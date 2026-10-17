# Maintenance — referans yazıcı fiziksel test takip çizelgesi

[English](maintenance-reference-printer-acceptance.md) · [JSON kaynak](maintenance-reference-printer-acceptance.json) · [Test kataloğu](maintenance-test-catalog_TR.md)

> **KALICI GELİŞTİRME / KABUL KAYDI.** Sonraki sohbet ve geliştirme aşamalarında önce bu dosyayı ve yanındaki JSON kaydını oku. Bu dosya yalnızca bir referans yazıcı içindir; kullanıcıya özel donanım kimlikleri genel Petrel koduna eklenmez.

**Kanıt sınırı:** 15 Ekim 2026 tarihli bağımsız 121-ID cihaz referansı, 16 Ekim 2026 Moonraker/Petrel keşif günlüğü ve açık kullanıcı gözlemleri. Günlükte **54 keşfedilmiş özellik** bulunduğu doğrulanmıştır, ancak bunların **tek tek ID dökümü** mevcut değildir. Aşağıdaki `confirmed` kayıtlar bağımsız referansla doğrulanmış *potansiyel yeteneklerdir*, canlı 54-ID listesinin eksiksiz kaydı olduğu iddia edilmez. `conditional` maddeler şu an çalıştırılabilir keşif olarak kabul edilmez.

**Temel ayrım:** Donanımın varlığı ≠ uygulanmış test adaptörü ≠ CI PASS ≠ gerçek yazıcıda kullanıcı kabulü. Önceki sürümler dahil açıkça doğrulanmış **12 adet** fiziksel test KABUL sayılır. **F02'nin 2 saniyelik kademeleri, O04'ün senkron dört renk testi ve F12'nin adaptif beş kademeli araması 16 Ekim 2026'da kullanıcı tarafından kabul edildi.** Önceki sonuçlar JSON geçmişinde korunmuştur; son LCD sonucu ve elektronik geri yükleme okuması ayrıca bildirilmedi. Bir cihaz veya eksen onaylanınca aynı ID altındaki diğer hedeflere PASS aktarılmaz.

**Cihaz bazlı durum:** **70 kayıt / 48 ID** — 12 KABUL, 52 BEKLİYOR, 5 KOŞULLU, 1 N/A. **F12'nin adaptif iterasyonları gerçek yazıcıda çalıştı ve LCD PASS bildirdi; kesin PWM eşiği paylaşılmadı. F02/O04 için son elektronik geri yükleme ayrıca doğrulanmadı.**

**Her onaylanan testin ardından (zorunlu):** ilgili JSON kaydındaki hedefin `status` alanını `accepted` yap; `acceptance` içine tarih, kullanıcı kanıtı, yürütücü sonucu ve `restore_verified` ekle. Ardından bu TR/EN tablolarında **yalnız o hedefin** kutucuğunu `[x]` yap. Aynı commit'te ilgili regresyonları güncelle; bot imzası ve **imzalı HEAD** CI PASS almadan tamamlandı deme. Gerçek fiziksel kabul olmadan hiçbir satıra `[x]` konamaz. Kullanıcı açıkça istemedikçe `master` merge edilmez.

**Özellikle hariç tutulanlar:** Yalnız bilgi okuyan S01/S02/S03/S05/S08/S10 ve H11/H14/M09/P09 vb. `INFORMATION` tanılamaları fiziksel PASS değildir. Tachometresiz fan için RPM ölçümü yapılmış sayılmaz. Z sanal endstop elle basılan fiziksel anahtar değildir. BLTouch yoktur; servo-probe vardır. R02 yalnız X/Y sensörüyle eşleşmiştir. Geçici `PFAB_Bucket_Percentage` bu referansın dışında; genel keşif kodu için kullanıcıya özel filtre değildir.

**17 Ekim kayıt kabulü:** S15 fiziksel enkoder (iki yön + basma), S16 beş renk ve S17 10/50/100% parlaklık; her birinde açık `observe(true)`, `PASSED_USER` ve kontrolcünün restore kanıtı var. Oturum `dec3042495ca4ab78b58b947e2b3c73a`. P03/P04 otomatik ölçüm sonuçları ayrıca kaydedildi; fiziksel kabul verilmedi. [Ayrıntılı kayıt incelemesi](maintenance-acceptance-2026-10-17_TR.md). İkinci oturumda M01 fiziksel X/Y endstop'ları da `open → TRIGGERED → open` ve açık kullanıcı onayıyla kabul edildi.

## Kullanıcı tarafından tamamlananlar

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [x] | F01 | `fan` | Parça soğutma fanının dönmesi | Hazır | **KABUL** |
| [x] | F02 | `fan` | Parça soğutma fanı hız kademeleri | Hazır | **KABUL (2 sn/kademe)** |
| [x] | F12 | `fan` | Adaptif beş kademeli fan kalkış PWM eşiği | Hazır | **KABUL (iterasyon / LCD PASS)** |
| [x] | S18 | `pwm_cycle_time Buzzer` | Buzzer ses testi | Hazır | **KABUL** |
| [x] | O03 | `output_pin case_light` | Güvenli yardımcı çıkış | Hazır | **KABUL** |
| [x] | O04 | `neopixel mmu_leds` | Adreslenebilir LED testi | Hazır | **KABUL (kırmızı → yeşil → mavi → beyaz)** |
| [x] | S15 | `Petrel encoder` | Petrel enkoder tanılama | Kullanıcı gördü; restore doğrulandı | **KABUL** |
| [x] | S16 | `DWIN LCD` | LCD tanılama | Kullanıcı gördü; restore doğrulandı | **KABUL** |
| [x] | S17 | `DWIN backlight` | LCD arka ışık testi | Kullanıcı gördü; restore doğrulandı | **KABUL** |
| [x] | M01 | `physical X endstop` | Fiziksel endstop basma/bırakma | Kullanıcı onayı; serbest durum doğrulandı | **KABUL** |
| [x] | M01 | `physical Y endstop` | Fiziksel endstop basma/bırakma | Kullanıcı onayı; serbest durum doğrulandı | **KABUL** |
| [x] | M03 | `Cartesian X/Y/Z homing` | Homing tamamlanması | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |

## Fiziksel test için hazır donanım — adaptör/kabul bekleyenler

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | H01 | `extruder` | Isıtıcının sıcaklık yükseltmesi | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H01 | `heater_bed` | Isıtıcının sıcaklık yükseltmesi | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H02 | `extruder` | Hotend PID kalibrasyonu | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H03 | `heater_bed` | Tabla PID kalibrasyonu | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H05 | `extruder` | Isınma hızı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H05 | `heater_bed` | Isınma hızı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H06 | `extruder` | Hedef sıcaklığa ulaşma süresi | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H06 | `heater_bed` | Hedef sıcaklığa ulaşma süresi | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H07 | `extruder` | Sıcaklık aşımı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H07 | `heater_bed` | Sıcaklık aşımı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H08 | `extruder` | Sıcaklık kararlılığı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H08 | `heater_bed` | Sıcaklık kararlılığı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H09 | `extruder` | Soğuma hızı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H09 | `heater_bed` | Soğuma hızı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H13 | `extruder` | Isıtıcı tepki uyarısı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | H13 | `heater_bed` | Isıtıcı tepki uyarısı | Hazır; toplu kabul bekliyor | **BEKLİYOR** |
| [ ] | M04 | `stepper_x` | Step motoru kaba hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M04 | `stepper_y` | Step motoru kaba hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M04 | `stepper_z` | Step motoru kaba hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M05 | `axis X` | Eksen kaba hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M05 | `axis Y` | Eksen kaba hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M05 | `axis Z` | Eksen kaba hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M06 | `axis X` | Haricî ölçümle eksen mesafesi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M06 | `axis Y` | Haricî ölçümle eksen mesafesi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M06 | `axis Z` | Haricî ölçümle eksen mesafesi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 stepper_x` | TMC sürücü durumu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 stepper_y` | TMC sürücü durumu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 stepper_z` | TMC sürücü durumu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M07 | `tmc2208 extruder` | TMC sürücü durumu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 stepper_x` | TMC hata bitleri | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 stepper_y` | TMC hata bitleri | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 stepper_z` | TMC hata bitleri | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M10 | `tmc2208 extruder` | TMC hata bitleri | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M12 | `endstop_phase X` | Endstop phase kalibrasyonu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | M12 | `endstop_phase Y` | Endstop phase kalibrasyonu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | P01 | `probe` | Prob tetikleme | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | P03 | `probe` | Prob tekrarlanabilirliği | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | P04 | `probe` | Tek prob ölçümü | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | P05 | `probe Z-offset` | Prob Z-offset sihirbazı | Leveling’de; Maintenance dışında | **BEKLİYOR** |
| [ ] | P07 | `bed_mesh (probe)` | Otomatik tabla mesh | Leveling’de; Maintenance dışında | **BEKLİYOR** |
| [ ] | P08 | `bed_mesh (manual)` | Manuel tabla mesh | Leveling’de; Maintenance dışında | **BEKLİYOR** |
| [ ] | P11 | `screws_tilt_adjust` | Vida tilt ayarı | Leveling’de; Maintenance dışında | **BEKLİYOR** |
| [ ] | R01 | `adxl345` | İvmeölçer verisi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | R02 | `resonance_tester X` | Eksen rezonansı | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | R02 | `resonance_tester Y` | Eksen rezonansı | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | R03 | `adxl345` | İvmeölçer gürültü tabanı | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | R04 | `input_shaper X/Y` | Input shaper kalibrasyonu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | E01 | `extruder filament path` | Kaba filament ekstrüzyonu | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | E02 | `extruder measured length` | Ölçülmüş ekstrüzyon mesafesi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | E03 | `filament_switch_sensor mmu_gate_sensor` | Filament var/yok sensörü | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | E07 | `extruder + MMU filament path` | Filament yolu hareketi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |
| [ ] | E11 | `Happy Hare MMU gate sensors (4 gates)` | MMU gate sensör testi | Hazır; fiziksel kabul bekliyor | **BEKLİYOR** |

## Ek kanıt veya güvenli entegrasyon gerektirenler

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | F13 | `guarded fan/heater comparison` | Fan termal A/B karşılaştırması | Geliştirilecek | **KOŞULLU** |
| [ ] | H15 | `co-located calibrated sensor pair` | Eşlenmiş sıcaklık sensörü sapması | Geliştirilecek | **KOŞULLU** |
| [ ] | E12 | `Happy Hare gear and selector` | MMU mekanik tanılama | Hazır; fiziksel kabul bekliyor | **KOŞULLU** |
| [ ] | O02 | `approved servo and deploy/stow path` | Güvenli servo hareketi | Hazır; fiziksel kabul bekliyor | **KOŞULLU** |
| [ ] | O06 | `user-defined physical servicing` | Kılavuzlu bakım | Hazır; fiziksel kabul bekliyor | **KOŞULLU** |

## Donanımı bulunmayanlar

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | F04 | `fan_generic (not installed)` | Genel fanın dönmesi | Hazır | **N/A** |

## Fiziksel kabul kanıtı

| ID / hedef | Kullanıcı gözlemi / güvenli sonuç | Yürütücü sonucu | `restore_verified` |
|---|---|---|---|
| F01 / `fan` | Fan çalıştı ve önceki raporlanan durumuna geri döndü. | `PASSED_USER` | `true` |
| F02 / `fan` | Yeni 2 sn/kademe sürümü kullanıcı tarafından kabul edildi; önceki kabul ve sonuçsuz deneme JSON geçmişinde korundu. | `OBSERVED_USER` (LCD sonucu ayrıca bildirilmedi) | `false` (ayrıca doğrulanmadı) |
| F12 / `fan` | Kick-start etkisi giderildikten sonra adaptif beş kademeli iterasyonlar gerçek yazıcıda çalıştı, LCD PASS gösterdi. Kesin PWM eşiği paylaşılmadı. | `PASSED_USER` (kullanıcının bildirdiği LCD PASS) | `true` (controller başarı yolu; bağımsız fiziksel ölçüm yok) |
| S18 / `pwm_cycle_time Buzzer` | Buzzer sesi duyuldu; Klipper PWM geri okuması yok. | `OBSERVED_USER` | `false` |
| O03 / `output_pin case_light` | Kasa ışığı değişti; önceki raporlanan durumu doğrulandı. | `PASSED_USER` | `true` |
| O04 / `neopixel mmu_leds` | Senkron kırmızı → yeşil → mavi → beyaz testi kullanıcı tarafından kabul edildi; önceki denemeler JSON geçmişinde korundu. | `OBSERVED_USER` (LCD sonucu ayrıca bildirilmedi) | `false` (ayrıca doğrulanmadı) |

## Sıradaki uygulama

**F12 uygulaması ve bu referans fan hedefinin kullanıcı kabulü tamamlandı.** Sıradaki bekleyen testler için bağımsız keşif, fiziksel güvenlik ve geri yükleme kuralları gerekir. Kalkış eşik komutundan ölçülmüş RPM veya elektriksel PWM çıkarılmaz. Koşullu donanım *otomatik olarak güvenli veya çalıştırılabilir* sayılmaz.

**H uygulama durumu:** Referans yazıcının 16 fiziksel H hedefinin adaptörleri hazır; hiçbirinin fiziksel kabulü henüz yapılmadı. Toplu test sırası ve H01–H18 kapsamı için [termal rehber](maintenance-thermal_TR.md).

**M uygulama durumu:** 22 doğrulanmış M hedefinde adaptör mevcut; M01 fiziksel X/Y endstopları ve M03 XYZ homing kabul edildi. M07 yalnız bilgi adaptörüdür, motor sağlığı PASS'i değildir. H kabul durumları bu geliştirmeyle değiştirilmedi. [Hareket rehberi](maintenance-motion_TR.md).

**P/R/E/S/O geliştirme kaydı (17 Ekim 2026):** Grup adaptörleri ve regresyonları eklendi; hiçbir yeni fiziksel kabul verilmedi. Probe Calibration, Bed Mesh ve Screws Tilt mevcut Leveling’de kalır. Koşullu profil/kaynak gereksinimleri sürer. Rehberler: [P](maintenance-probe_TR.md), [R](maintenance-resonance_TR.md), [E](maintenance-filament_TR.md), [S](maintenance-system_TR.md), [O](maintenance-auxiliary_TR.md). Genel bütünleştirme bu çalışmaya dahil değildir.

**M03 fiziksel kabul (17 Ekim):** `a4ad65170ed04b649b0a1a58c9c55b53` oturumunda `observe(true)` #220, `PASSED_USER` #222 ve `restore_verified=true`. Son okuma: `homed_axes=xyz`, X=157.9, Y=141.5, Z=10 mm. 274 olayda kayıp/yazma hatası yok; güvenlik durdurması veya UI işleyici hatası kaydedilmedi.

**M03 UI akış kusuru:** İlk iki onay (#97/#114) eskiyen 3 saniyelik güvenlik kanıtı nedeniyle ön kontrole dönüp seçimi Cancel'a sıfırladı; yalnız üçüncü onay (#129) hareketi başlattı. Fiziksel homing kabulü UI akışının kabulü değildir. Kullanıcı bildirimi üzerine aynı hareket onayını taze güvenlik kontrolünden sonra koruma ve belirgin akış tanılama eklendi; sonraki kayıtta tek onayla yenileme ve gönderim doğrulandı (aşağıda).

**Sonraki kayıt (17 Ekim, `b04c94981b594e06b991b254996a34a0`):** 330 sıralı olay, kayıp/yazma hatası yok; dönen iki dosya birlikte incelendi. M03 tek onay #96 → güvenlik yenileme #102 → gönderim isteği #105 → kullanıcı gözlemi #191 → PASSED_USER #193, geri yükleme doğru. Sonuçtan Self Tests'e dönüş Back girdisiyle #197'de gerçekleşti. M04 X de tek onayla yenilendi; #231 komut isteği, #233 genel Future hatası, #235 Petrel güvenlik durdurması, #241 INCONCLUSIVE. Genel hata metni nedeniyle tel üzerinden gönderim/Klipper cevabı ile gönderim öncesi guard reddi ayırt edilemiyor; kök neden kesin değil. M04 kabul edilmedi. Tanılama artık gönderim aşaması, son guard nedeni, güvenli sunucu hata kategorisi/kodu, motor etkinliği ve sınırlı mesh/hız verilerini tutar. Sonraki fiziksel denemeye kadar M04 çalışma düzeltmesi doğrulanmış sayılmaz.

**Otomatik homing kaydı (17 Ekim):** `8bf95a8e7cc6431c99ede09170b26605`, HEAD `4e2f713`, 448 olay, kayıp/yazma hatası yok. M04/X tek onay #120 ile gerekli homing'i tamamlayıp asıl teste geçti. #295, gönderim öncesi guard reddini ve clear_mesh_before_motion_test nedenini kesinleştirdi; test komutu socket'e yazılmadı. Sonraki #297 shutdown Petrel tarafından gereksiz istendi, #303 INCONCLUSIVE oldu. Boş [[]] mesh gösterimi ve kesin gönderim öncesi reddin shutdown'a dönüşmesi düzeltildi. M04 kabul verilmedi; önceki M03 kabulü değişmedi.
