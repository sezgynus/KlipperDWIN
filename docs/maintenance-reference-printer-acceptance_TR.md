# Maintenance — referans yazıcı fiziksel test takip çizelgesi

[English](maintenance-reference-printer-acceptance.md) · [JSON kaynak](maintenance-reference-printer-acceptance.json) · [Test kataloğu](maintenance-test-catalog_TR.md)

> **KALICI GELİŞTİRME / KABUL KAYDI.** Sonraki sohbet ve geliştirme aşamalarında önce bu dosyayı ve yanındaki JSON kaydını oku. Bu dosya yalnızca bir referans yazıcı içindir; kullanıcıya özel donanım kimlikleri genel Petrel koduna eklenmez.

**Kanıt sınırı:** 15 Ekim 2026 tarihli bağımsız 121-ID cihaz referansı, 16 Ekim 2026 Moonraker/Petrel keşif günlüğü ve açık kullanıcı gözlemleri. Günlükte **54 keşfedilmiş özellik** bulunduğu doğrulanmıştır, ancak bunların **tek tek ID dökümü** mevcut değildir. Aşağıdaki `confirmed` kayıtlar bağımsız referansla doğrulanmış *potansiyel yeteneklerdir*, canlı 54-ID listesinin eksiksiz kaydı olduğu iddia edilmez. `conditional` maddeler şu an çalıştırılabilir keşif olarak kabul edilmez.

**Temel ayrım:** Donanımın varlığı ≠ uygulanmış test adaptörü ≠ CI PASS ≠ gerçek yazıcıda kullanıcı kabulü. Önceki sürümler dahil açıkça doğrulanmış **5 adet** fiziksel test KABUL sayılır. **F02'nin yeni 2 saniyelik kademeleri ve O04'ün senkron dört renk testi 16 Ekim 2026'da kullanıcı tarafından kabul edildi.** Önceki sonuçlar JSON geçmişinde korunmuştur; son LCD sonucu ve elektronik geri yükleme okuması ayrıca bildirilmedi. Bir cihaz veya eksen onaylanınca aynı ID altındaki diğer hedeflere PASS aktarılmaz.

**Cihaz bazlı durum:** **70 kayıt / 48 ID** — 5 KABUL (F02 eski sürümü), 56 BEKLİYOR, 8 KOŞULLU, 1 N/A. **F02 ve O04 yeni sürümleri kullanıcı tarafından kabul edildi; son elektronik geri yükleme ayrıca doğrulanmadı.**

**Her onaylanan testin ardından (zorunlu):** ilgili JSON kaydındaki hedefin `status` alanını `accepted` yap; `acceptance` içine tarih, kullanıcı kanıtı, yürütücü sonucu ve `restore_verified` ekle. Ardından bu TR/EN tablolarında **yalnız o hedefin** kutucuğunu `[x]` yap. Aynı commit'te ilgili regresyonları güncelle; bot imzası ve **imzalı HEAD** CI PASS almadan tamamlandı deme. Gerçek fiziksel kabul olmadan hiçbir satıra `[x]` konamaz. Kullanıcı açıkça istemedikçe `master` merge edilmez.

**Özellikle hariç tutulanlar:** Yalnız bilgi okuyan S01/S02/S03/S05/S08/S10 ve H11/H14/M09/P09 vb. `INFORMATION` tanılamaları fiziksel PASS değildir. Tachometresiz fan için RPM ölçümü yapılmış sayılmaz. Z sanal endstop elle basılan fiziksel anahtar değildir. BLTouch yoktur; servo-probe vardır. R02 yalnız X/Y sensörüyle eşleşmiştir. Geçici `PFAB_Bucket_Percentage` bu referansın dışında; genel keşif kodu için kullanıcıya özel filtre değildir.

## Kullanıcı tarafından tamamlananlar

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [x] | F01 | `fan` | Parça soğutma fanının dönmesi | Hazır | **KABUL** |
| [x] | F02 | `fan` | Parça soğutma fanı hız kademeleri | Hazır | **KABUL (2 sn/kademe)** |
| [x] | S18 | `pwm_cycle_time Buzzer` | Buzzer ses testi | Hazır | **KABUL** |
| [x] | O03 | `output_pin case_light` | Güvenli yardımcı çıkış | Hazır | **KABUL** |
| [x] | O04 | `neopixel mmu_leds` | Adreslenebilir LED testi | Hazır | **KABUL (kırmızı → yeşil → mavi → beyaz)** |

## Fiziksel test için hazır donanım — adaptör/kabul bekleyenler

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | F12 | `fan` | Fanın dönebildiği en düşük PWM | Geliştirilecek | **BEKLİYOR** |
| [ ] | H01 | `extruder` | Isıtıcının sıcaklık yükseltmesi | Geliştirilecek | **BEKLİYOR** |
| [ ] | H01 | `heater_bed` | Isıtıcının sıcaklık yükseltmesi | Geliştirilecek | **BEKLİYOR** |
| [ ] | H02 | `extruder` | Hotend PID kalibrasyonu | Geliştirilecek | **BEKLİYOR** |
| [ ] | H03 | `heater_bed` | Tabla PID kalibrasyonu | Geliştirilecek | **BEKLİYOR** |
| [ ] | H05 | `extruder` | Isınma hızı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H05 | `heater_bed` | Isınma hızı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H06 | `extruder` | Hedef sıcaklığa ulaşma süresi | Geliştirilecek | **BEKLİYOR** |
| [ ] | H06 | `heater_bed` | Hedef sıcaklığa ulaşma süresi | Geliştirilecek | **BEKLİYOR** |
| [ ] | H07 | `extruder` | Sıcaklık aşımı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H07 | `heater_bed` | Sıcaklık aşımı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H08 | `extruder` | Sıcaklık kararlılığı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H08 | `heater_bed` | Sıcaklık kararlılığı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H09 | `extruder` | Soğuma hızı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H09 | `heater_bed` | Soğuma hızı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H13 | `extruder` | Isıtıcı tepki uyarısı | Geliştirilecek | **BEKLİYOR** |
| [ ] | H13 | `heater_bed` | Isıtıcı tepki uyarısı | Geliştirilecek | **BEKLİYOR** |
| [ ] | M01 | `physical X endstop` | Fiziksel endstop basma/bırakma | Geliştirilecek | **BEKLİYOR** |
| [ ] | M01 | `physical Y endstop` | Fiziksel endstop basma/bırakma | Geliştirilecek | **BEKLİYOR** |
| [ ] | M03 | `Cartesian X/Y/Z homing` | Homing tamamlanması | Geliştirilecek | **BEKLİYOR** |
| [ ] | M04 | `stepper_x` | Step motoru kaba hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M04 | `stepper_y` | Step motoru kaba hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M04 | `stepper_z` | Step motoru kaba hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M05 | `axis X` | Eksen kaba hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M05 | `axis Y` | Eksen kaba hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M05 | `axis Z` | Eksen kaba hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M06 | `axis X` | Haricî ölçümle eksen mesafesi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M06 | `axis Y` | Haricî ölçümle eksen mesafesi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M06 | `axis Z` | Haricî ölçümle eksen mesafesi | Geliştirilecek | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 stepper_x` | TMC sürücü durumu | Geliştirilecek | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 stepper_y` | TMC sürücü durumu | Geliştirilecek | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 stepper_z` | TMC sürücü durumu | Geliştirilecek | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 extruder` | TMC sürücü durumu | Geliştirilecek | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 stepper_x` | TMC hata bitleri | Geliştirilecek | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 stepper_y` | TMC hata bitleri | Geliştirilecek | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 stepper_z` | TMC hata bitleri | Geliştirilecek | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 extruder` | TMC hata bitleri | Geliştirilecek | **BEKLİYOR** |
| [ ] | M12 | `endstop_phase X` | Endstop phase kalibrasyonu | Geliştirilecek | **BEKLİYOR** |
| [ ] | M12 | `endstop_phase Y` | Endstop phase kalibrasyonu | Geliştirilecek | **BEKLİYOR** |
| [ ] | P01 | `probe` | Prob tetikleme | Geliştirilecek | **BEKLİYOR** |
| [ ] | P03 | `probe` | Prob tekrarlanabilirliği | Geliştirilecek | **BEKLİYOR** |
| [ ] | P04 | `probe` | Tek prob ölçümü | Geliştirilecek | **BEKLİYOR** |
| [ ] | P05 | `probe Z-offset` | Prob Z-offset sihirbazı | Geliştirilecek | **BEKLİYOR** |
| [ ] | P07 | `bed_mesh (probe)` | Otomatik tabla mesh | Geliştirilecek | **BEKLİYOR** |
| [ ] | P08 | `bed_mesh (manual)` | Manuel tabla mesh | Geliştirilecek | **BEKLİYOR** |
| [ ] | P11 | `screws_tilt_adjust` | Vida tilt ayarı | Geliştirilecek | **BEKLİYOR** |
| [ ] | R01 | `adxl345` | İvmeölçer verisi | Geliştirilecek | **BEKLİYOR** |
| [ ] | R02 | `resonance_tester X` | Eksen rezonansı | Geliştirilecek | **BEKLİYOR** |
| [ ] | R02 | `resonance_tester Y` | Eksen rezonansı | Geliştirilecek | **BEKLİYOR** |
| [ ] | R03 | `adxl345` | İvmeölçer gürültü tabanı | Geliştirilecek | **BEKLİYOR** |
| [ ] | R04 | `input_shaper X/Y` | Input shaper kalibrasyonu | Geliştirilecek | **BEKLİYOR** |
| [ ] | E01 | `extruder filament path` | Kaba filament ekstrüzyonu | Geliştirilecek | **BEKLİYOR** |
| [ ] | E02 | `extruder measured length` | Ölçülmüş ekstrüzyon mesafesi | Geliştirilecek | **BEKLİYOR** |
| [ ] | E03 | `filament_switch_sensor mmu_gate_sensor` | Filament var/yok sensörü | Geliştirilecek | **BEKLİYOR** |
| [ ] | E07 | `extruder + MMU filament path` | Filament yolu hareketi | Geliştirilecek | **BEKLİYOR** |
| [ ] | E11 | `Happy Hare MMU gate sensors (4 gates)` | MMU gate sensör testi | Geliştirilecek | **BEKLİYOR** |

## Ek kanıt veya güvenli entegrasyon gerektirenler

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | F13 | `guarded fan/heater comparison` | Fan termal A/B karşılaştırması | Geliştirilecek | **KOŞULLU** |
| [ ] | H15 | `co-located calibrated sensor pair` | Eşlenmiş sıcaklık sensörü sapması | Geliştirilecek | **KOŞULLU** |
| [ ] | E12 | `Happy Hare gear and selector` | MMU mekanik tanılama | Geliştirilecek | **KOŞULLU** |
| [ ] | S15 | `Petrel encoder` | Petrel enkoder tanılama | Geliştirilecek | **KOŞULLU** |
| [ ] | S16 | `DWIN LCD` | LCD tanılama | Geliştirilecek | **KOŞULLU** |
| [ ] | S17 | `DWIN backlight` | LCD arka ışık testi | Geliştirilecek | **KOŞULLU** |
| [ ] | O02 | `approved servo and deploy/stow path` | Güvenli servo hareketi | Geliştirilecek | **KOŞULLU** |
| [ ] | O06 | `user-defined physical servicing` | Kılavuzlu bakım | Geliştirilecek | **KOŞULLU** |

## Donanımı bulunmayanlar

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | F04 | `fan_generic (not installed)` | Genel fanın dönmesi | Hazır | **N/A** |

## Fiziksel kabul kanıtı

| ID / hedef | Kullanıcı gözlemi / güvenli sonuç | Yürütücü sonucu | `restore_verified` |
|---|---|---|---|
| F01 / `fan` | Fan çalıştı ve önceki raporlanan durumuna geri döndü. | `PASSED_USER` | `true` |
| F02 / `fan` | Yeni 2 sn/kademe sürümü kullanıcı tarafından kabul edildi; önceki kabul ve sonuçsuz deneme JSON geçmişinde korundu. | `OBSERVED_USER` (LCD sonucu ayrıca bildirilmedi) | `false` (ayrıca doğrulanmadı) |
| S18 / `pwm_cycle_time Buzzer` | Buzzer sesi duyuldu; Klipper PWM geri okuması yok. | `OBSERVED_USER` | `false` |
| O03 / `output_pin case_light` | Kasa ışığı değişti; önceki raporlanan durumu doğrulandı. | `PASSED_USER` | `true` |
| O04 / `neopixel mmu_leds` | Senkron kırmızı → yeşil → mavi → beyaz testi kullanıcı tarafından kabul edildi; önceki denemeler JSON geçmişinde korundu. | `OBSERVED_USER` (LCD sonucu ayrıca bildirilmedi) | `false` (ayrıca doğrulanmadı) |

## Sıradaki uygulama

**Önce O04 Happy Hare metin-bayrak uyumluluğunu gerçek yazıcıda yeniden test et; F02 `fan` güncel sonuç kaydını da doğruladıktan sonra F12'ye geç.** Her kademede gerçek kullanıcı gözlemi şarttır; PWM komutu RPM ölçümü değildir. Isıtıcı, mekanik hareket, probe ve MMU için kendi özel güvenlik/geri yükleme adaptörleri kurulmadan komut gönderilmez. Uygun olmayan veya sırf koşullu donanıma ait satırlar *otomatik güvenli test* değildir.
