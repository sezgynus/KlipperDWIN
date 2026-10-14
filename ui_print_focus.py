"""Print-focused views with bounded, field-only rendering and quiet edits."""
import time
import textwrap
import math
from functools import lru_cache
from concurrent.futures import Future
from collections.abc import Mapping
from graphite_theme import show_icon
from lcd_resources import (ICON_PRINT_TUNE, ICON_PRINT_PAUSE, ICON_PRINT_RESUME,
                           ICON_PRINT_STOP, ICON_PRINT_MMU, ICON_JOB_SWITCH_OFF,
                           ICON_JOB_SWITCH_ON, ICON_PRINT_TUNE_WIDE,
                           ICON_PRINT_CLOSE, PRINT_BUTTON_SELECTED,
                           ICON_STOP_BUTTON_NORMAL, ICON_STOP_BUTTON_SELECTED,
                           ICON_STOP_BUTTON_DANGER, ICON_STOP_PANEL,
                           ICON_MMU_ERROR_SELECTED, ICON_MMU_ERROR_NORMAL,
                           ICON_APPLY_BUTTON)


@lru_cache(maxsize=64)
def _focus_round_caps(width, radius):
    """Opaque one-bit top/bottom caps for a native bitmap fill."""
    row_bytes = (width + 7) // 8
    rows = []
    for y in range(radius):
        dx = math.isqrt(radius * radius - (radius - y) ** 2)
        inset = radius - dx
        bits = ((1 << (width - 2 * inset)) - 1) << inset
        rows.append((bits << (row_bytes * 8 - width)).to_bytes(row_bytes, 'big'))
    limit = max(1, (248 - 10) // row_bytes)

    def chunks(lines):
        return tuple((offset, b''.join(lines[offset:offset + limit]))
                     for offset in range(0, len(lines), limit))
    return chunks(rows), chunks(tuple(reversed(rows)))




class PrintFocusMixin:
    TuneEdit = 70
    PrintErrorDetails = 71

    def _focus_text(self, text, x, y, font=None, color=None, bg=None):
        self.lcd.draw_text(False, False, self.lcd.font8x16 if font is None else font,
                           self.lcd.Color_White if color is None else color,
                           self.lcd.Color_Bg_Black if bg is None else bg, x, y, str(text))

    def _focus_round(self, x, y, w, h, color, radius=5):
        # Two native fills plus bitmap corner caps, not 4x software circles.
        # The graphics have no text; labels remain runtime-rendered.
        radius = max(0, min(int(radius), w // 2, h // 2))
        if radius == 0:
            self.lcd.draw_rectangle(1, color, x, y, x+w-1, y+h-1)
            return
        self.lcd.draw_rectangle(1, color, x+radius, y, x+w-radius-1, y+h-1)
        self.lcd.draw_rectangle(1, color, x, y+radius, x+w-1, y+h-radius-1)
        top, bottom = _focus_round_caps(w, radius)
        for offset, bitmap in top:
            self.lcd.draw_bitmap(x, y+offset, w, color, self.lcd.Color_Bg_Black, bitmap)
        for offset, bitmap in bottom:
            self.lcd.draw_bitmap(x, y+h-radius+offset, w,
                                 color, self.lcd.Color_Bg_Black, bitmap)

    @staticmethod
    def _focus_time(seconds):
        minutes = max(0, int(seconds or 0)) // 60
        return '%02d:%02d' % (minutes//60, minutes%60)

    def _focus_mmu(self):
        return self.pd.mmu_session.state

    def _focus_error(self):
        m = self._focus_mmu()
        return str(m.reason or self.pd.mmu_session.message or 'MMU needs attention') if m and m.locked else ''

    def _focus_color(self, tool):
        m = self._focus_mmu()
        if m and isinstance(tool, int) and 0 <= tool < len(m.ttg_map):
            gate = m.ttg_map[tool]
            if isinstance(gate, int) and 0 <= gate < len(m.colors):
                color = m.colors[gate]
                try:
                    value = int(str(color).lstrip('#'), 16)
                    return ((value>>19)&31)<<11 | ((value>>10)&63)<<5 | ((value>>3)&31)
                except (ValueError, TypeError):
                    pass
        cache=getattr(self,'_thumbnail_cache',None)
        details=cache.details.get(getattr(self,'_print_thumbnail_key',None)) if cache else None
        if details:
            f=next((f for f in details.filaments if f.tool==tool),None)
            if f and f.color is not None:return f.color
        return 0x7BEF

    def _focus_material(self):
        m = self._focus_mmu()
        if not m:
            cache=getattr(self,'_thumbnail_cache',None)
            details=cache.details.get(getattr(self,'_print_thumbnail_key',None)) if cache else None
            if details and len(details.filaments)==1:
                f=details.filaments[0]
                return '%s / single extruder'%f.material, 'T%d %s'%(f.tool,f.material), f.tool
            return 'Single extruder', '', None
        tool = m.tool
        material = '--'
        if isinstance(tool, int) and 0 <= tool < len(m.ttg_map):
            gate = m.ttg_map[tool]
            if isinstance(gate, int) and 0 <= gate < len(m.materials):
                material = m.materials[gate] or '--'
        return '%s / %d tools' % (material, m.num_gates), 'T%s %s' % (tool if tool is not None and tool >= 0 else '?', material), tool

    def _focus_buttons(self):
        terminal = self.pd.status in ('complete', 'cancelled')
        middle = 'MMU' if self._focus_error() else ('Resume' if self._focus_paused() else 'Pause')
        return ([('Tune', ICON_PRINT_TUNE_WIDE), ('Close', ICON_PRINT_CLOSE)]
                if terminal else
                [('Tune', ICON_PRINT_TUNE),
                 (middle, {'Pause': ICON_PRINT_PAUSE, 'Resume': ICON_PRINT_RESUME,
                           'MMU': ICON_PRINT_MMU}[middle]),
                 ('Stopping' if getattr(self, '_stop_waiting', False) else 'Stop',
                  ICON_PRINT_STOP)])

    def _focus_paused(self):
        pending = getattr(self, '_quiet_edits', {}).get('pause')
        return bool(pending['target']) if pending else self.pd.printingIsPaused()

    def _focus_draw_buttons(self):
        buttons = self._focus_buttons()
        limit = len(buttons) - (2 if buttons[-1][0] == 'Stopping' else 1)
        self.select_print.now = min(self.select_print.now, limit)
        width = 119 if len(buttons) == 2 else 78
        shape = (len(buttons), width)
        cache = getattr(self, '_focus_button_render', {})
        layout_changed = shape != getattr(self, '_focus_button_shape', None)
        if layout_changed:
            # A layout transition can leave the old third button behind.
            # Ordinary selections/state changes never erase the control strip.
            self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 14, 311, 258, 349)
            cache = {}
            self._focus_button_shape = shape
        for i, (label, normal) in enumerate(buttons):
            disabled = label == 'Stopping'
            selected = self.select_print.now == i and not disabled
            color = (0x7BEF if disabled else 0xFBCB if label == 'Stop'
                     and not selected else self.lcd.Color_White)
            start = getattr(self, '_quiet_blinks', {}).get('pause')
            if i == 1 and start is not None and int((time.monotonic()-start)/.2)%2 == 0:
                color = 0xFBCB
            token = (normal, label, selected, color)
            if cache.get(i) == token:
                continue
            x = 14+i*(width+5)
            # Clear this button only: filtered JPEG corners must not retain
            # the previous selection's color or label pixels.
            if not layout_changed:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, x, 312, x+width-1, 347)
            show_icon(self.lcd, self.ICON,
                      PRINT_BUTTON_SELECTED[normal] if selected else normal, x, 312)
            char_width = 8 if len(label)*8+20 <= width else 6
            text_x = x + (width-(len(label)*char_width+20))//2 + 20
            self._focus_text(label, text_x, 322 if char_width == 8 else 324,
                             font=self.lcd.font8x16 if char_width == 8 else self.lcd.font6x12,
                             color=color)
            cache[i] = token
        self._focus_button_render = cache


    def _focus_print_open(self):
        self.checkkey = self.PrintProcess
        self.Clear_Main_Window()
        self.Draw_Title('Print')
        self._focus_render = {}
        self._focus_button_shape = None
        self._focus_button_render = {}
        self._focus_preview_drawn = None
        self._focus_print_tick(force=True)
        self.Draw_Status_Area(False)

    def _focus_field(self, key, value, x, y, w, h, draw):
        cache = self._focus_render
        if cache.get(key) != value:
            self.lcd.draw_rectangle(1,self.lcd.Color_Bg_Black,x,y,x+w-1,y+h-1)
            draw()
            cache[key] = value

    def _focus_print_tick(self, force=False):
        self._focus_tick_quiet()
        if not hasattr(self, '_focus_render'): self._focus_render = {}
        name = str(self.pd.file_name or '').rsplit('/',1)[-1]
        self._focus_field('name',name,14,42,244,16,lambda:self._focus_text(name[:30],14,42))
        material, label, tool = self._focus_material()
        self._focus_field('material',material,14,62,244,16,lambda:self._focus_text(material[:30],14,62,color=0xADB5))
        percent = max(0,min(100,int(self.pd.getPercent())))
        self._focus_field('percent',percent,128,90,130,27,lambda:self._focus_text('%d%%'%percent,128,93,self.lcd.font12x24))
        remaining = self._focus_time(self.pd.remain())
        self._focus_field('remain',remaining,128,125,130,42,lambda:(self._focus_text('Remaining',128,125,color=0xADB5),self._focus_text(remaining,128,145,self.lcd.font10x20)))
        layers = self.pd.print_layers()
        self._focus_field('layers',layers,128,173,130,13,lambda:self._focus_text('Layer %d/%d'%layers if layers else '',128,174,self.lcd.font6x12,color=0xADB5))
        self._focus_field('progress',percent,14,190,244,8,lambda:self._draw_progress_track(self.lcd,14,190,244,percent))
        elapsed = self._focus_time(self.pd.duration())
        self._focus_field('elapsed',elapsed,14,210,110,44,lambda:(self._focus_text('Elapsed',14,210,color=0xADB5),self._focus_text(elapsed,14,232,self.lcd.font10x20)))
        finish = 'Finish ~'+time.strftime('%H:%M',time.localtime(time.time()+max(0,self.pd.remain()))) if self.pd.status=='printing' else self.pd.status.capitalize()
        self._focus_field('finish',finish,128,210,130,17,lambda:self._focus_text(finish[:16],128,210,color=0xADB5))
        raw = self.pd.state.status.get('mmu',{})
        change = raw.get('toolchange', {})
        source = raw.get('last_tool', change.get('from_tool') if isinstance(change, Mapping) else None)
        target = change.get('next_tool') if isinstance(change, Mapping) else None
        # Happy Hare versions expose next_tool directly; use it only with a real source.
        target = raw.get('next_tool',target)
        m = self._focus_mmu()
        if source is None and m and m.action.lower() not in ('idle','unknown'): source=tool
        changing = bool(m) and all(isinstance(v,int) and not isinstance(v,bool) and 0<=v<m.num_gates for v in (source,target)) and source!=target
        token = (label,tool,self._focus_color(tool),source,target,changing)
        def draw_filament():
            if changing:
                self.lcd.fill_circle(self._focus_color(source),134,243,5)
                self._focus_text('T%d >'%source,145,234)
                self.lcd.fill_circle(self._focus_color(target),200,243,5)
                self._focus_text('T%d'%target,211,234)
            elif label:
                self.lcd.fill_circle(self._focus_color(tool),134,243,5)
                self._focus_text(label[:14],145,234)
        self._focus_field('filament',token,128,232,130,25,draw_filament)
        error = self._focus_error()
        state = error or (m.action if m and m.action.lower() not in ('idle','unknown') else ('Happy Hare ready' if m else 'Single extruder'))
        state_key = (state, error, self.pd.status)
        if self._focus_render.get('state') != state_key:
            self._focus_state_panel(state, error)
            self._focus_render['state'] = state_key
        start=getattr(self,'_quiet_blinks',{}).get('pause')
        blink=start is not None and int((time.monotonic()-start)/.2)%2==0
        buttons=(tuple(self._focus_buttons()),self.select_print.now,blink)
        if self._focus_render.get('buttons')!=buttons:
            self._focus_draw_buttons()
            self._focus_render['buttons'] = (tuple(self._focus_buttons()),
                                             self.select_print.now, blink)
        if force:
            self._focus_round(14,90,88,88,0x2967,8)
            self._focus_text('Preview',30,124,self.lcd.font6x12,color=0xADB5)
        self._sync_thumbnail_cache()
        key=getattr(self,'_print_thumbnail_key',None)
        if key:
            self._thumbnail_cache.tick(self.lcd,foreground=key,chunks=2)
            address=self._thumbnail_cache.address(key)
            if address is not None and self._focus_preview_drawn != (key,address):
                self.lcd.draw_rectangle(1,self.lcd.Color_Bg_Black,14,90,101,177)
                self.lcd.show_sram_jpeg(14,90,address,background=False,enhanced=True)
                self._focus_preview_drawn=(key,address)

    def _focus_state_panel(self, state, error):
        background = 0x40E5 if error else 0x2967
        if self._focus_render.get('state_backing') != background:
            self._focus_round(14, 266, 244, 38, background, 7)
            self._focus_render['state_backing'] = background
        else:
            # Keep round edges intact. Clear only the two dynamic text lines.
            self.lcd.draw_rectangle(1, background, 22, 270, 253, 300)
        self._focus_text(('MMU: ' + state)[:28] if error
                         else self.pd.status.capitalize(), 24, 272,
                         self.lcd.font6x12, color=0xFBCB if error else 0xFFFF)
        self._focus_text('Click MMU to read / recover' if error else state[:29],
                         24, 287, self.lcd.font6x12, color=0xADB5)

    def _focus_print_input(self):
        event=self.get_encoder_state()
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            delta=getattr(self,"_rotation_steps",1)*(1 if event==self.ENCODER_DIFF_CW else -1)
            buttons = self._focus_buttons()
            limit = len(buttons) - (2 if buttons[-1][0] == 'Stopping' else 1)
            self.select_print.now = max(0, min(limit, self.select_print.now + delta))
            self._focus_draw_buttons()
        elif event==self.ENCODER_DIFF_ENTER:
            label=self._focus_buttons()[self.select_print.now][0]
            if label == 'Stopping':
                return  # Inactive control: never re-submit cancellation.
            if label=='Tune':
                self.checkkey=self.Tune;self.select_tune.reset();self._focus_tune_open()
            elif label=='MMU':
                self._focus_error_open()
            elif label in ('Pause','Resume'):
                target=label=='Pause'
                self._focus_submit('pause',target,lambda:(self.pd.pause_job if target else self.pd.resume_job)(report_error=False))
                self._focus_draw_buttons()
            elif label=='Stop':
                self.checkkey=self.Print_window
                self.pd.HMI_flag.select_flag=False
                self.Popup_window_PauseOrStop()
            else:
                self.pd.HMI_flag.done_confirm_flag=False
                self._acknowledged_terminal=self._terminal_key();self.Goto_MainMenu()
        self.lcd.update()

    def _focus_submit(self,key,target,submit):
        if not hasattr(self,'_quiet_edits'): self._quiet_edits={}
        if not hasattr(self,'_quiet_blinks'): self._quiet_blinks={}
        actual={s.key:s.value for s in self.pd.print_settings()}
        old=self.pd.printingIsPaused() if key=='pause' else actual.get(key)
        try: future=submit()
        except Exception:
            self._quiet_edits.pop(key,None);self._quiet_blinks[key]=time.monotonic()
            if hasattr(self,'_loop'):self._loop.set_interval(.1)
            return
        self._quiet_edits[key]={'target':target,'old':old,'future':future,'epoch':self.pd.state.epoch,'accepted':None}

    def _focus_tick_quiet(self):
        now=time.monotonic()
        pending=getattr(self,'_quiet_edits',{})
        values={s.key:s.value for s in self.pd.print_settings()} if pending else {}
        values['pause']=self.pd.printingIsPaused()
        for key,p in tuple(pending.items()):
            if p['epoch']!=self.pd.state.epoch or key not in values:
                del pending[key];continue
            future=p['future']
            if isinstance(future,Future) and future.done() and (future.cancelled() or future.exception()):
                del pending[key];self._quiet_blinks[key]=now
            elif abs(values[key]-p['target'])<.00001:
                del pending[key]
            elif isinstance(future,Future) and future.done():
                if p['accepted'] is None: p['accepted']=now
                # A delayed reply alone is never treated as rejection. After a
                # completed command, reconcile against subscribed printer state.
                elif self.pd.state.ready and now-p['accepted']>8:
                    del pending[key];self._quiet_blinks[key]=now
        self._quiet_blinks={k:v for k,v in getattr(self,'_quiet_blinks',{}).items() if now-v<.8}
        if self._quiet_blinks and hasattr(self,'_loop'):self._loop.set_interval(.1)

    def _focus_tune_open(self):
        self.checkkey=self.Tune
        self._sync_fan_animation(False)
        self.Clear_Popup_Area();self.Draw_Title('Tune')
        self._focus_tune_render={};self._focus_tune_shape=None
        self._focus_tune_tick()

    def _focus_tune_rows(self):
        rows=[(None,38)]
        group=None;y=64
        for s in self.pd.print_settings():
            if s.group!=group: group=s.group;y+=14
            rows.append((s,y));y+=20
        return rows

    def _focus_tune_tick(self):
        self._focus_tick_quiet()
        rows=self._focus_tune_rows()
        shape=tuple((s.key if s else '',y) for s,y in rows)
        if shape!=getattr(self,'_focus_tune_shape',None):
            self.lcd.draw_rectangle(1,self.lcd.Color_Bg_Black,0,31,271,479)
            self._focus_tune_render={};self._focus_tune_shape=shape
            group=None
            for s,y in rows:
                if s and s.group!=group:
                    group=s.group;self._focus_text(group,14,y-14,self.lcd.font6x12,color=0x063B)
        self.select_tune.now=min(self.select_tune.now,len(rows)-1)
        cache=self._focus_tune_render
        now=time.monotonic()
        for i,(s,y) in enumerate(rows):
            selected=i==self.select_tune.now
            value=getattr(self,'_quiet_edits',{}).get(s.key,{}).get('target',s.value) if s else None
            start=getattr(self,'_quiet_blinks',{}).get(s.key) if s else None
            red=start is not None and int((now-start)/.2)%2==0
            token=(selected,value,red)
            key=s.key if s else 'back'
            if cache.get(key)==token:continue
            self.lcd.draw_rectangle(1,self.lcd.Color_Bg_Black,10,y,261,y+23 if s is None else y+19)
            bg=0x2967 if selected else self.lcd.Color_Bg_Black
            if selected:self._focus_round(10,y,252,24 if s is None else 20,bg,5)
            self._focus_text(s.label if s else '< Back',18,y+2)
            if s:
                color=0xFBCB if red else 0x063B
                if s.toggle:
                    show_icon(self.lcd,self.ICON,ICON_JOB_SWITCH_ON if value else ICON_JOB_SWITCH_OFF,226,y+4)
                    if red:self.lcd.draw_rectangle(0,color,224,y+2,255,y+17)
                else:
                    text=('%.*f'%(s.decimals,value))+s.unit
                    self._focus_text(text,254-len(text)*8,y+2,color=color)
            cache[key]=token

    def _focus_tune_input(self):
        event=self.get_encoder_state();rows=self._focus_tune_rows()
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            self.select_tune.now=max(0,min(len(rows)-1,self.select_tune.now+getattr(self,"_rotation_steps",1)*(1 if event==self.ENCODER_DIFF_CW else -1)))
            self._focus_tune_tick()
        elif event==self.ENCODER_DIFF_ENTER:
            s=rows[self.select_tune.now][0]
            if s is None:self.Goto_PrintProcess()
            elif s.toggle:
                target=not bool(getattr(self,'_quiet_edits',{}).get(s.key,{}).get('target',s.value))
                self._focus_submit(s.key,int(target),lambda:self.pd.set_print_setting(s.key,int(target),report_error=False));self._focus_tune_tick()
            else:
                self._tune_edit=s
                self._tune_target=getattr(self,'_quiet_edits',{}).get(s.key,{}).get('target',s.value)
                self.checkkey=self.TuneEdit;self._focus_edit_draw()
        self.lcd.update()

    def _focus_edit_draw(self):
        self.Clear_Popup_Area();self.Draw_Title('Adjust')
        s=self._tune_edit
        self._focus_text(s.group,18,74,self.lcd.font6x12,color=0x063B)
        self._focus_text(s.label,18,96)
        self._focus_edit_value()
        self._focus_text('Turn to adjust',80,228)
        show_icon(self.lcd, self.ICON, ICON_APPLY_BUTTON, 32, 284)
        self._focus_text('Apply',116,294,color=0x10C4)

    def _focus_edit_value(self):
        self.lcd.draw_rectangle(1,self.lcd.Color_Bg_Black,14,156,257,204)
        s=self._tune_edit;text=('%.*f'%(s.decimals,self._tune_target))+s.unit
        self._focus_text(text,(272-len(text)*12)//2,167,self.lcd.font12x24)

    def _focus_edit_input(self):
        event=self.get_encoder_state();s=self._tune_edit
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            delta=s.step*getattr(self,'_encoder_move_value',1)*(1 if event==self.ENCODER_DIFF_CW else -1)
            self._tune_target=round(max(s.minimum,min(s.maximum,self._tune_target+delta)),s.decimals)
            heater = (self.pd.capabilities.active_hotend if s.key.startswith('nozzle@')
                      else self.pd.capabilities.bed if s.key == 'bed' else None)
            if heater and 0 < self._tune_target < heater.minimum:
                self._tune_target = heater.minimum if delta > 0 else 0
            self._focus_edit_value()
        elif event==self.ENCODER_DIFF_ENTER:
            target=self._tune_target
            self._focus_submit(s.key,target,lambda:self.pd.set_print_setting(s.key,target,report_error=False))
            self.checkkey=self.Tune;self._focus_tune_open()
        self.lcd.update()

    def _focus_error_open(self):
        self._focus_full_error=self._focus_error()
        self._focus_error_scroll=0;self._focus_error_choice=0;self.checkkey=self.PrintErrorDetails
        self._focus_error_draw()

    def _focus_error_draw(self, *, viewport_only=False, buttons_only=False):
        if not viewport_only and not buttons_only:
            self.Clear_Popup_Area()
            self.Draw_Title('MMU error')
            self._focus_error_lines = textwrap.wrap(self._focus_full_error, 30) or ['MMU needs attention']
            self._focus_text('Turn: scroll full error', 14, 376,
                             self.lcd.font6x12, color=0xADB5)
        if not buttons_only:
            if viewport_only:
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black,
                                        12, 45, 260, 348)
            for i, line in enumerate(self._focus_error_lines[
                    self._focus_error_scroll:self._focus_error_scroll + 15]):
                self._focus_text(line, 14, 48 + i * 20)
        if not viewport_only:
            for i, label in enumerate(('MMU recovery', 'Back')):
                y = 410 + i * 34
                icon = ICON_MMU_ERROR_SELECTED if self._focus_error_choice == i else ICON_MMU_ERROR_NORMAL
                show_icon(self.lcd, self.ICON, icon, 14, y)
                self._focus_text(label, (272 - len(label) * 8) // 2,
                                 y + 7, color=0x10C4 if self._focus_error_choice == i else 0xFFFF)

    def _focus_error_input(self):
        event = self.get_encoder_state()
        previous_scroll = self._focus_error_scroll
        previous_choice = self._focus_error_choice
        maximum = max(0, len(self._focus_error_lines) - 15)
        if event == self.ENCODER_DIFF_CW:
            target = self._focus_error_scroll + getattr(self,'_rotation_steps',1)
            self._focus_error_scroll = min(maximum,target)
            if target > maximum: self._focus_error_choice = 1
        elif event == self.ENCODER_DIFF_CCW:
            steps = getattr(self,'_rotation_steps',1)
            if self._focus_error_choice:
                self._focus_error_choice = 0
                steps -= 1
            self._focus_error_scroll = max(0,self._focus_error_scroll-steps)
        elif event == self.ENCODER_DIFF_ENTER:
            if self._focus_error_choice:
                self.Goto_PrintProcess()
            else:
                self._mmu_return_print = True
                self.Enter_MMU_Menu('recover')
            return
        if self._focus_error_scroll != previous_scroll:
            self._focus_error_draw(viewport_only=True)
            self.lcd.update()
        if self._focus_error_choice != previous_choice:
            self._focus_error_draw(buttons_only=True)
            self.lcd.update()

    def _focus_stop_draw(self, buttons_only=False):
        if not buttons_only:
            self.Clear_Main_Window()
            self.Draw_Title('Stop print')
            show_icon(self.lcd, self.ICON, ICON_STOP_PANEL, 14, 106)
            self._focus_text('Cancel this print?',36,132,self.lcd.font10x20)
            self._focus_text('The print cannot resume.',40,184)
        for yes,label,x in ((False,'Back',26),(True,'Stop',142)):
            selected=bool(self.pd.HMI_flag.select_flag)==yes
            icon = ICON_STOP_BUTTON_DANGER if yes and selected else (
                ICON_STOP_BUTTON_SELECTED if selected else ICON_STOP_BUTTON_NORMAL)
            show_icon(self.lcd, self.ICON, icon, x, 244)
            self._focus_text(label,x+36,254)

    def _focus_stop_input(self):
        event=self.get_encoder_state()
        if event in (self.ENCODER_DIFF_CW,self.ENCODER_DIFF_CCW):
            selected = event == self.ENCODER_DIFF_CW
            if bool(self.pd.HMI_flag.select_flag) != selected:
                self.pd.HMI_flag.select_flag = selected
                self._focus_stop_draw(buttons_only=True)
        elif event==self.ENCODER_DIFF_ENTER:
            if self.pd.HMI_flag.select_flag:
                future = self._action(
                    'Cancel', self.pd.cancel_job,
                    lambda: self.pd.status == 'cancelled',
                    confirmation_timeout=None, silent=True,
                    on_accept=self._restore_action_screen)
                if future is not None:
                    self._stop_waiting = True
                    # The print dashboard remains live; only Stop becomes
                    # 'Stopping' and cannot be selected or pressed again.
                    self.Goto_PrintProcess()
            else:self.Goto_PrintProcess()
        self.lcd.update()
