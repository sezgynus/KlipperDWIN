# Maintenance — referans yazıcı fiziksel test takip çizelgesi

[English](maintenance-reference-printer-acceptance.md) · [JSON kaynak](maintenance-reference-printer-acceptance.json) · [Test kataloğu](maintenance-test-catalog_TR.md)

> **KALICI GELİŞTİRME / KABUL KAYDI.** Sonraki sohbet ve geliştirme aşamalarında önce bu dosyayı ve yanındaki JSON kaydını oku. Bu dosya yalnızca bir referans yazıcı içindir; kullanıcıya özel donanım kimlikleri genel Petrel koduna eklenmez.

**Kanıt sınırı:** 15 Ekim 2026 tarihli bağımsız 121-ID cihaz referansı, 16 Ekim 2026 Moonraker/Petrel keşif günlüğü ve açık kullanıcı gözlemleri. Günlükte **54 keşfedilmiş özellik** bulunduğu doğrulanmıştır, ancak bunların **tek tek ID dökümü** mevcut değildir. Aşağıdaki `confirmed` kayıtlar bağımsız referansla doğrulanmış *potansiyel yeteneklerdir*, canlı 54-ID listesinin eksiksiz kaydı olduğu iddia edilmez. `conditional` maddeler şu an çalıştırılabilir keşif olarak kabul edilmez.

**Temel ayrım:** Donanımın varlığı ≠ uygulanmış test adaptörü ≠ CI PASS ≠ gerçek yazıcıda kullanıcı kabulü. Önceki sürümler dahil açıkça doğrulanmış **55 adet** referans yazıcı yeteneği kullanıcı tarafından kabul edilmiştir: 51 Maintenance hedefi ve dört mevcut Leveling işlevi. Leveling kabulü Maintenance adaptörü oluşturmaz. **F02'nin 2 saniyelik kademeleri, O04'ün senkron dört renk testi ve F12'nin adaptif beş kademeli araması 16 Ekim 2026'da kullanıcı tarafından kabul edildi.** Önceki sonuçlar JSON geçmişinde korunmuştur; son LCD sonucu ve elektronik geri yükleme okuması ayrıca bildirilmedi. Bir cihaz veya eksen onaylanınca aynı ID altındaki diğer hedeflere PASS aktarılmaz.

**Cihaz bazlı durum:** **62 kayıt / 46 ID** — 55 KABUL, 1 BEKLİYOR, 5 KOŞULLU, 1 N/A. **F12'nin adaptif iterasyonları gerçek yazıcıda çalıştı ve LCD PASS bildirdi; kesin PWM eşiği paylaşılmadı. F02/O04 için son elektronik geri yükleme ayrıca doğrulanmadı.**

**Kabul türleri:** Termal karakterizasyonda *test prosedürünün kabulü*, yazıcının termal performans kriterini geçmesi demek değildir. H07/H08 Extruder sonuçları `FAILED_METRIC` olarak korunur; doğru ölçüm ve güvenli tamamlanma sayesinde prosedürler kabul edilir.

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
| [x] | M04 | `stepper_x` | Step motoru kaba hareketi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M04 | `stepper_y` | Step motoru kaba hareketi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M04 | `stepper_z` | Step motoru kaba hareketi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M05 | `axis X` | Eksen kaba hareketi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M05 | `axis Y` | Eksen kaba hareketi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M05 | `axis Z` | Eksen kaba hareketi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M06 | `axis X` | Haricî ölçümle eksen mesafesi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M06 | `axis Y` | Haricî ölçümle eksen mesafesi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M06 | `axis Z` | Haricî ölçümle eksen mesafesi | Kullanıcı gözlemi; geri yükleme doğrulandı | **KABUL** |
| [x] | M12 | `endstop_phase X` | Endstop phase kalibrasyonu | On homing, bekleyen 49/64 | **KABUL** |
| [x] | M12 | `endstop_phase Y` | Endstop phase kalibrasyonu | On homing, bekleyen 33/64 | **KABUL** |
| [x] | H01 | `extruder` | Isıtıcının sıcaklık yükseltmesi | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H01 | `heater_bed` | Isıtıcının sıcaklık yükseltmesi | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H05 | `extruder` | Isınma hızı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H05 | `heater_bed` | Isınma hızı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H06 | `extruder` | Hedef sıcaklığa ulaşma süresi | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H06 | `heater_bed` | Hedef sıcaklığa ulaşma süresi | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H07 | `extruder` | Sıcaklık aşımı | Tek döngü; OFF doğrulandı | **KABUL (prosedür; FAILED_METRIC)** |
| [x] | H07 | `heater_bed` | Sıcaklık aşımı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H08 | `extruder` | Sıcaklık kararlılığı | Tek döngü; OFF doğrulandı | **KABUL (prosedür; FAILED_METRIC)** |
| [x] | H08 | `heater_bed` | Sıcaklık kararlılığı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H09 | `extruder` | Soğuma hızı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H09 | `heater_bed` | Soğuma hızı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H13 | `extruder` | Isıtıcı tepki uyarısı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H13 | `heater_bed` | Isıtıcı tepki uyarısı | Tek döngü; OFF doğrulandı | **KABUL (prosedür)** |
| [x] | H02 | `extruder` | Hotend PID kalibrasyonu | Klipper PID, katsayılar + OFF doğrulandı | **KABUL** |
| [x] | H03 | `heater_bed` | Tabla PID kalibrasyonu | Klipper PID, katsayılar + OFF doğrulandı | **KABUL** |
| [x] | P01 | `probe` | Prob tetikleme | Üç taze durum okuması; servo geri toplama tamamlandı | **KABUL** |
| [x] | P03 | `probe` | Prob tekrarlanabilirliği | 10 ölçüm; aralık 0,0175 mm, σ=0,004644 mm | **KABUL** |
| [x] | P04 | `probe` | Tek prob ölçümü | Ölçüm ve otomatik güvenli Z yükseltme kullanıcı tarafından doğrulandı | **KABUL (ölçüm + yükseltme)** |
| [x] | P05 | `probe Z-offset` | Prob Z-offset sihirbazı | Mevcut Leveling; Maintenance adaptörü yok | **KABUL (Leveling)** |
| [x] | P07 | `bed_mesh (probe)` | Otomatik tabla mesh | Mevcut Leveling; Maintenance adaptörü yok | **KABUL (Leveling)** |
| [x] | P08 | `bed_mesh (manual)` | Manuel tabla mesh | Mevcut Leveling; Maintenance adaptörü yok | **KABUL (Leveling)** |
| [x] | P11 | `screws_tilt_adjust` | Vida tilt ayarı | Mevcut Leveling; Maintenance adaptörü yok | **KABUL (Leveling)** |
| [x] | R01 | `adxl345` | İvmeölçer verisi | ACCELEROMETER_QUERY; üç eksen ölçümü doğrulandı | **KABUL** |
| [x] | R03 | `adxl345` | İvmeölçer gürültü tabanı | MEASURE_AXES_NOISE 2 sn; XYZ PSD ölçüldü | **KABUL** |
| [x] | R02 | `resonance_tester X` | Eksen rezonansı | TEST_RESONANCES; Klipper PSD ve kullanıcı onayı | **KABUL** |
| [x] | R02 | `resonance_tester Y` | Eksen rezonansı | TEST_RESONANCES; Klipper PSD ve kullanıcı onayı | **KABUL** |
| [x] | R04 | `input_shaper X/Y` | Klipper input shaper kalibrasyonu | X: 3hump_ei 137,6 Hz; Y: MZV 42,2 Hz; kaydedilmedi | **KABUL** |
| [x] | E07 | `extruder + MMU filament path` | Filament yolu hareketi | 5 mm sürme / PASSED_USER | **KABUL** |
| [x] | E02 | `extruder measured length` | Ölçülmüş ekstrüzyon mesafesi | 10 mm girildi; hesaplanan fark 0 mm | **KABUL** |
| [x] | E01 | `extruder filament path` | Kaba filament ekstrüzyonu | 5 mm filament sürme / PASSED_USER | **KABUL** |
| [x] | E03 | `filament_switch_sensor mmu_gate_sensor` | Filament var/yok sensörü | Kullanıcı doğruladı; yeni trace paylaşılmadı | **KABUL** |

## Fiziksel test için hazır donanım — adaptör/kabul bekleyenler

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | E11 | `Happy Hare MMU gate sensors (4 gates)` | MMU gate sensör testi | Adaptör askıda; elle MMU kapatma yasak | **BEKLİYOR** |

## Ek kanıt veya güvenli entegrasyon gerektirenler

| Yapıldı | ID | Hedef | Özellik | Adapter | Durum |
|---|---|---|---|---|---|
| [ ] | F13 | `guarded fan/heater comparison` | Fan termal A/B karşılaştırması | Geliştirilecek | **KOŞULLU** |
| [ ] | H15 | `co-located calibrated sensor pair` | Eşlenmiş sıcaklık sensörü sapması | Geliştirilecek | **KOŞULLU** |
| [ ] | E12 | `Happy Hare gear and selector` | MMU mekanik tanılama | Adaptör askıda; eksik mekanik doğrulama | **KOŞULLU** |
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
| P01 / `probe` | Kullanıcı açıkça üç durum geçişinin ve prob geri toplamasının çalıştığını doğruladı. | `PASSED` | `true` |
| P03 / `probe` | Kullanıcı 10 ölçümlü testi kabul etti; aralık 0,0175 mm, σ 0,004644 mm. | `PASSED` | `false` (gerekli geri yükleme kanıtı yok) |
| P04 / `probe` | İlk manuel Z yükseltme sonrasında −0,025 mm ölçüldü. Kullanıcı 18 Ekim'de P04 otomatik güvenli Z kaldırmayı ayrıca yeniden deneyerek doğruladı; eski trace bunu içermiyordu. | `PASSED` (ilk); `OBSERVED_USER` (yeni gözlem) | `false` (bağımsız Z restore okuması yok) |
| P05 / `probe Z-offset` | Kullanıcı önceden çalışan Leveling işlevini onayladı; yeni Maintenance trace/adaptör yok. | `OBSERVED_USER` (Leveling) | `false` (bağımsız doğrulama yok) |
| P07 / `bed_mesh (probe)` | Kullanıcı önceden çalışan Leveling işlevini onayladı; yeni Maintenance trace/adaptör yok. | `OBSERVED_USER` (Leveling) | `false` (bağımsız doğrulama yok) |
| P08 / `bed_mesh (manual)` | Kullanıcı önceden çalışan Leveling işlevini onayladı; yeni Maintenance trace/adaptör yok. | `OBSERVED_USER` (Leveling) | `false` (bağımsız doğrulama yok) |
| P11 / `screws_tilt_adjust` | Kullanıcı önceden çalışan Leveling işlevini onayladı; yeni Maintenance trace/adaptör yok. | `OBSERVED_USER` (Leveling) | `false` (bağımsız doğrulama yok) |
| R01 / `adxl345` | Kullanıcı testin tamamlandığını bildirdi; kontrolcü PASSED, XYZ sayısal ivme değerleri görüldü. Bağımsız kalibrasyon iddiası yok. | `PASSED` | `false` (salt okuma) |
| R03 / `adxl345` | Kullanıcı testin tamamlandığını bildirdi; kontrolcü PASSED, üç eksende sayısal gürültü PSD değerleri görüldü. Gürültü kalite eşiği iddia edilmez. | `PASSED` | `false` (salt okuma) |

## Sıradaki uygulama

**F12 uygulaması ve bu referans fan hedefinin kullanıcı kabulü tamamlandı.** Sıradaki bekleyen testler için bağımsız keşif, fiziksel güvenlik ve geri yükleme kuralları gerekir. Kalkış eşik komutundan ölçülmüş RPM veya elektriksel PWM çıkarılmaz. Koşullu donanım *otomatik olarak güvenli veya çalıştırılabilir* sayılmaz.

**H uygulama durumu:** Referans yazıcının 16 fiziksel H hedefinin adaptörleri hazır; hiçbirinin fiziksel kabulü henüz yapılmadı. Toplu test sırası ve H01–H18 kapsamı için [termal rehber](maintenance-thermal_TR.md).

**M uygulama durumu:** 14 doğrulanmış M fiziksel hedefinde adaptör mevcut; 14 hedef kullanıcı tarafından kabul edildi. M07'nin dört cihazı yalnız Diagnostics kapsamındadır ve fiziksel kabul listesinde değildir. H kabul durumları bu geliştirmeyle değiştirilmedi. [Hareket rehberi](maintenance-motion_TR.md).

**P/R/E/S/O geliştirme kaydı (17 Ekim 2026):** Grup adaptörleri ve regresyonları eklendi; hiçbir yeni fiziksel kabul verilmedi. Probe Calibration, Bed Mesh ve Screws Tilt mevcut Leveling’de kalır. Koşullu profil/kaynak gereksinimleri sürer. Rehberler: [P](maintenance-probe_TR.md), [R](maintenance-resonance_TR.md), [E](maintenance-filament_TR.md), [S](maintenance-system_TR.md), [O](maintenance-auxiliary_TR.md). Genel bütünleştirme bu çalışmaya dahil değildir.

**M03 fiziksel kabul (17 Ekim):** `a4ad65170ed04b649b0a1a58c9c55b53` oturumunda `observe(true)` #220, `PASSED_USER` #222 ve `restore_verified=true`. Son okuma: `homed_axes=xyz`, X=157.9, Y=141.5, Z=10 mm. 274 olayda kayıp/yazma hatası yok; güvenlik durdurması veya UI işleyici hatası kaydedilmedi.

**M03 UI akış kusuru:** İlk iki onay (#97/#114) eskiyen 3 saniyelik güvenlik kanıtı nedeniyle ön kontrole dönüp seçimi Cancel'a sıfırladı; yalnız üçüncü onay (#129) hareketi başlattı. Fiziksel homing kabulü UI akışının kabulü değildir. Kullanıcı bildirimi üzerine aynı hareket onayını taze güvenlik kontrolünden sonra koruma ve belirgin akış tanılama eklendi; sonraki kayıtta tek onayla yenileme ve gönderim doğrulandı (aşağıda).

**Sonraki kayıt (17 Ekim, `b04c94981b594e06b991b254996a34a0`):** 330 sıralı olay, kayıp/yazma hatası yok; dönen iki dosya birlikte incelendi. M03 tek onay #96 → güvenlik yenileme #102 → gönderim isteği #105 → kullanıcı gözlemi #191 → PASSED_USER #193, geri yükleme doğru. Sonuçtan Self Tests'e dönüş Back girdisiyle #197'de gerçekleşti. M04 X de tek onayla yenilendi; #231 komut isteği, #233 genel Future hatası, #235 Petrel güvenlik durdurması, #241 INCONCLUSIVE. Genel hata metni nedeniyle tel üzerinden gönderim/Klipper cevabı ile gönderim öncesi guard reddi ayırt edilemiyor; kök neden kesin değil. M04 kabul edilmedi. Tanılama artık gönderim aşaması, son guard nedeni, güvenli sunucu hata kategorisi/kodu, motor etkinliği ve sınırlı mesh/hız verilerini tutar. Sonraki fiziksel denemeye kadar M04 çalışma düzeltmesi doğrulanmış sayılmaz.

**Otomatik homing kaydı (17 Ekim):** `8bf95a8e7cc6431c99ede09170b26605`, HEAD `4e2f713`, 448 olay, kayıp/yazma hatası yok. M04/X tek onay #120 ile gerekli homing'i tamamlayıp asıl teste geçti. #295, gönderim öncesi guard reddini ve clear_mesh_before_motion_test nedenini kesinleştirdi; test komutu socket'e yazılmadı. Sonraki #297 shutdown Petrel tarafından gereksiz istendi, #303 INCONCLUSIVE oldu. Boş [[]] mesh gösterimi ve kesin gönderim öncesi reddin shutdown'a dönüşmesi düzeltildi. M04 kabul verilmedi; önceki M03 kabulü değişmedi.

**Hareket toplu kabulü (17 Ekim):** `3e8f0231f5a84e8eaeae6944aba6951d`, HEAD `537e037`: 2545 kesintisiz olay, kayıp/yazma hatası yok. M04/M05/M06 X/Y/Z (9 hedef) açık gözlem + PASSED_USER + geri yükleme doğrulamasıyla kabul edildi. M06'da kullanıcı her eksene 10 mm girdi ve ayrı dönüş onayı verdi; bu bağımsız metroloji değildir. M12/X OBSERVED_USER ile kabul edildi; pending config kasıtlı kaldı, kaydedilmedi, sayısal faz eski sanitizer tarafından gizlendi. M10 X/Y/Z açık gözlem ve 0 raporlanan hata ile kabul edildi; motor sağlığı PASS'i değildir. İlk M04/X Not observed seçiminin yanlışlıkla yapıldığı kullanıcı tarafından açıklandı; fiziksel başarısızlık sayılmaz. Sonraki iki açık kabul geçerlidir. M05/Z bir kez kullanıcı tarafından hareket öncesi iptal edildi, sonra kabul edildi. M01/X yeniden geçti; önceki kabul değişmedi. M12/Y ve M10/extruder kabul edilmedi. Komut hatası/shutdown yok; tüm test ekranı çıkışları sonuç sayfasına gitti.

Sayısal trigger_phase kaybı düzeltildi: logger artık yalnız geçerli `0 <= faz < toplam <= 4096` biçimindeki kesri korur; dosya yolları hâlâ çıkarılır. Geçmişte gizlenmiş faz değeri uydurulmaz.

**Kullanıcı kabul düzeltmesi (17 Ekim):** Kullanıcı M10/M12'de Observed seçtiğini ancak testin anlamını bilmediğini, açıklama öncesinde kabul verilmemesini belirtti. M10 X/Y/Z ve M12/X kabulü geri alındı; önceki tıklamalar geçmişte geçersiz kabul olarak korunur. M04/M05/M06 kabulleri değişmez. Güncel toplam 21 kabul, 43 bekleyen, 5 koşullu, 1 N/A.

M10 yalnız TMC2208 drv_status hata/sıcaklık uyarı bayraklarını okur; hareket, yük altında test veya ayar yazımı yapmaz. Faults: none reported yalnız o anda raporlanan bayrak yok demektir. M12 mevcut homing faz istatistiğinden ENDSTOP_PHASE_CALIBRATE ile bekleyen trigger_phase üretir; doğrulanmış pending sonuç ve aynı konum/modlar aranır. SAVE_CONFIG gönderilmez; Observed sonucu kalıcı kaydetmez. Bu, bağımsız homing tekrarlanabilirlik ölçümü değildir. M12/Y önceki bekleyen ayarı korumak için engellenmişti.

**Son M12 kabulü (17 Ekim):** Kullanıcı eksen başına on homing akışını iki hedef için açıkça kabul etti. X oturumu `2a74f7fe73914463b7798c7551b51c92`, run 1, faz `49/64`, `OBSERVED_USER` #1088; Y oturumu `2fd812d7ffdb4c6e8b59275ef181b1b2`, run 2, faz `33/64`, `OBSERVED_USER` #771. Önceki geçersiz X onayı JSON geçmişinde korunmuştur. SAVE_CONFIG uygulanmadı; bağımsız hassasiyet ölçümü yapılmadı. Tekrar giriş ön kontrolü sorunu kabul bakımından açıkça göz ardı edildi. M10 hâlâ bekliyor. Yeni toplam: 23 kabul, 41 bekleyen, 5 koşullu, 1 N/A.

**M12/Y Diagnostics doğrulaması (17 Ekim 2026, LCD 19:18):** Kullanıcı, Y eksenini home ettikten sonra salt okunur M12/Y tanılamasının başarıyla çalıştığını açıkça doğruladı. Önceki `INCONCLUSIVE / no_valid_evidence` sonucu, o oturumda Y için homing geçmişi olmamasından kaynaklandı. Ekran görüntüsünde `OBSERVED`, `observed information`, `stepper_y.phase: 58/64` görülüyor. Bu değer mevcut `last_home` tanılama sonucudur; **yeni bir on homing'li M12 kalibrasyonu değildir ve önceki kabul edilmiş bekleyen `33/64` trigger_phase değerinin yerine geçmez**. M12/Y fiziksel kabulü korunur, kabul toplamları değişmez. Ekran görüntüsüyle doğrulanan tanılama, JSON'da M12/Y `diagnostic_observations` alanına ayrıca işlendi.

**M10 ayrılmış ID (17 Ekim 2026):** M10, yanlış sınıflandırılmış bir Self Test olduğu için gizli ve boş bırakıldı. Diğer numaralar kaydırılmadı. Sürücü hata durumu M07 Diagnostics altında salt okunur bilgi olarak sunulur, motor sağlığı PASS'i verilmez. M10 X/Y/Z önceki geçersiz kullanıcı gözlemleri ve Extruder bekleyen kaydı JSON geçmiş arşivinde korunur; aktif kabul çizelgesinde M10 satırı yoktur. Güncel durum: 66 kayıt, 23 kabul, 37 bekleyen, 5 koşullu, 1 uygulanamaz.

**M07 fiziksel kabul listesinden çıkarıldı (17 Ekim 2026):** X/Y/Z/Extruder için dört `M07` kaydı, Self Test değil salt okunur Diagnostics oldukları için aktif fiziksel kabul çizelgesinden çıkarıldı. Ayrı JSON `evidence.m07_informational_diagnostics` kaydı doğrudan `DRV_STATUS` okumalarını, kullanıcı doğrulamasını ve önceki dört bekleyen satırı arşivler. Yeni fiziksel PASS üretilmedi, mevcut 23 kabul ve M12 kayıtları değişmedi. Güncel toplam: **62 kayıt / 46 ID — 23 KABUL, 33 BEKLİYOR, 5 KOŞULLU, 1 N/A.**

**Termal karakterizasyon prosedür kabulü (17 Ekim 2026):** Oturum
`58240fb38284486dbb6cbdd3d45f6358`, imzalı HEAD `115e392`.
1.830 sıralı olay; kayıp/yazma hatası/shutdown yok.
Extruder tek döngü run 1, onay #792, sonuç #794; Bed tek döngü
run 2, onay #1660, sonuç #1662. Her iki döngüde hedef OFF,
güç sıfır ve soğuma doğrulandı (`restore_verified=true`).
H01/H05/H06/H07/H08/H09/H13 için iki cihazda **14 prosedür kabulü**
açık kullanıcı talimatıyla verildi; iki ayrı fiziksel çalıştırmadan
14 bağımsız test ölçümü ve kaydı elde edildi.
Extruder H07 ölçümü **7,72 °C sıcaklık aşımı** (`FAILED_METRIC`),
H08 ölçümü **6,69 °C kararlılık dalgalanması** (`FAILED_METRIC`);
**bu performans sonuçları değiştirilmiyor**. Bed 7/7 ve Extruder
5/7 metrik kriterini karşıladı. H02/H03 PID kabulü bu oturum sırasında hâlâ bekliyordu; sonraki ayrı H02 testi kabul edildi.
**Önceki termal karakterizasyon sonrası toplam: 62 kayıt / 46 ID — 37 KABUL, 19 BEKLİYOR,
5 KOŞULLU, 1 N/A.**

**H02 Extruder PID kabulü (17 Ekim 2026):** İzleme oturumu
`31cd66be65bd4a3b88968c920adfe340`, test edilen imzalı HEAD
`1b6511d`; 1.720 ardışık olay, sıfır kayıp ve yazma hatası,
bir dosya rotasyonu. H02 run 1, hedef 150 °C; Klipper
`PID_CALIBRATE` tamamlandı (#1352). Bekleyen PID değerleri
Kp=**14,738**, Ki=**0,558**, Kd=**97,273** olarak Petrel'de
doğru okundu. OFF/soğuma doğrulandı (`restore_verified=true`).
Kullanıcı `observe(true)` (#1595) verdi; sonuç #1597
`PASSED_USER`. **H02 fiziksel prosedürü kabul edildi.**
`SAVE_CONFIG` çalıştırılmadı; katsayılar kalıcı kaydedildi diye
iddia edilmez. H03 Bed PID run 2, H02'den kalan
`existing_or_unknown_pending_config` nedeniyle komut gönderilmeden
`BLOCKED` (#1672); H03 kabulü verilmedi.
**H02 kabulü sonrası toplam: 62 kayıt / 46 ID — 38 KABUL, 18 BEKLİYOR,
5 KOŞULLU, 1 N/A.**

**H03 Bed PID fiziksel kabulü (17 Ekim 2026):**
Oturum `8fa2b04372d94b7ca60e6d443fc098a8`, imzalı HEAD `1b6511d`.
2.671 olay (sıra 1721–4391); sıfır kayıp/yazma hatası, bir rotasyon.
H03 run 3, hedef 60 °C. PID_CALIBRATE gönderim #1792, tamamlanma #4118.
Yeni katsayılar: Kp=72,339; Ki=1,502; Kd=870,785.
Isıtıcı OFF/soğuma ve `restore_verified=true` doğrulandı.
Kullanıcı `observe(true)` (#4288) onayıyla `PASSED_USER` (#4290)
sonucunu verdi. H03 fiziksel test prosedürü kabul edildi.
`SAVE_CONFIG` çağrılmadı; kalıcı kaydetme doğrulanmadı.
Önceki H03 BLOCKED denemesi geçmişte korunur.
**Referans yazıcıda H grubunun 16/16 prosedürü kabul edildi.
Güncel toplam: 62 kayıt, 44 KABUL, 12 BEKLİYOR, 5 KOŞULLU, 1 N/A.**

## P grubu fiziksel kabulü ve P04 hazırlığı (17 Ekim 2026)

Kullanıcı P01, P03 ve P04'ün gerçek yazıcıda geçtiğini açıkça bildirdi. Trace `2d899dbe5dcc42e6a5e6a020df941369` (693 olay, 0 kayıp/yazma hatası) korunur. P04'ün eski kodunda Z=2,964 mm konumundaki ilk ön kontrol `raise_z_before_probe_test` ile BLOCKED olmuş, kullanıcı Z'yi 52,964 mm'ye yükselttikten sonra tek ölçüm başarıyla alınmıştır. Tek ölçüm prosedürü KABUL'dür; yeni otomatik Z kaldırma hazırlığı bu kayıt sırasında çalıştırılmamıştır ve ayrı fiziksel tekrar gerektirir.

## R01/R03 fiziksel kabulü ve P04 tekrar testi (17 Ekim 2026)

Kullanıcı P04, R01 ve R03 testlerini gerçek yazıcıda yaptığını bildirdi. `070d7f8524944245bec7259f58e3f6a3` oturumunda 672 olay, 0 kayıp/yazma hatası ve 1 rotasyon vardır; imzalı HEAD `15476fa8`. P04/PASSED #303, R01/PASSED #387 ve R03/PASSED #535 doğrulandı. P04 önce `G28` #119 ile homing yaptı, sonra `PROBE` #287 ile Z=-0,015 mm okudu. Yeni bağımsız düşük-Z yükseltme adımı **çalıştırılmadı**. R01 üç eksende sayısal ivme, R03 iki saniyelik MEASURE_AXES_NOISE üzerinden üç PSD verisi sağladı. R02 #457 ve R04 #431 kullanıcı tarafından iptal edildi/ABORTED; kabul verilmedi. R01/R03 sonuçları mutlak sensör kalibrasyonu veya geri yükleme iddiası taşımaz.

## 18 Ekim 2026 — mevcut Leveling kabulleri ve P04 Z yükseltme tekrarı

Kullanıcı P04'ü yeniden deneyerek otomatik güvenli Z yükseltmesinin çalıştığını doğruladı. Bu yeni gözlemdir; eski trace kayıtları değiştirilmedi ve yükseltme içermiyordu. P05, P07, P08 ve P11 önceden çalışan Leveling işlevleri olarak kabul edildi. Maintenance çalıştırma kapsamı ve adaptörleri dışında kalırlar. Yeni Leveling test trace'i, LCD PASS veya restore okuması iddia edilmez.

## 18 Ekim 2026 — Referans yazıcıda R grubu tamamlandı

Kullanıcı R grubunun tamamını açıkça kabul etti. `ff80258017ad4c1495e3fd1c64b17e7e` trace oturumu, imzalı HEAD `ad061591`: 902 olay, sıfır kayıp/yazma hatası/rotasyon. R02 X `TEST_RESONANCES` (#121) çalıştırdı; kullanıcı `observe(true)` (#177), kontrolcü `PASSED` (#179) bildirdi. R02 Y `TEST_RESONANCES` (#260), `observe(true)` (#305), `PASSED` (#307) ile tamamlandı. İki kabul de Klipper'ın PSD verisini kaydettiğini kanıtlar; **Petrel spektrumu puanlamaz veya shaper hesaplamaz**. Klipper'ın R04 X `SHAPER_CALIBRATE` (#355) sonucu `OBSERVED` (#439): **3hump_ei / 137,6 Hz**. R04 Y'nin ilk denemesi `existing_pending_config` sebebiyle `BLOCKED` (#519); yeni XYZ homing (#598) ardından `SHAPER_CALIBRATE` (#769) ile tekrarlandığında `OBSERVED` (#854): **MZV / 42,2 Hz**. Tek R04 kabul satırı her iki eksenin prosedürünü kapsar; `restore_verified=false`, `saved=false`. `SAVE_CONFIG` çalıştırılmadı, kalıcı kaydetme veya bağımsız en iyi mekanik ayar doğrulaması iddia edilmez. Önceki R01/R03 kabul kayıtları ve iptal edilmiş rezonans denemeleri korunur. **Güncel toplam: 62 kayıt / 46 ID — 51 KABUL, 5 BEKLİYOR, 5 KOŞULLU, 1 N/A.**

## 18 Ekim 2026 — E grubu kısmi kullanıcı kabulleri

Kullanıcı `d924a92a9df94f1b99645da43a7b14be` trace oturumunu göndererek tamamlanan E testlerinin kabul listesine işlenmesini açıkça istedi. İlgili oturum #903–1877 arasındadır (975 olay; kayıp/yazma hatası yok, bir dosya rotasyonu). ZIP içindeki `events.previous.jsonl` dosyasında eski oturumlar da bulunduğundan bunlar bu kabule karıştırılmadı. Test edilen imzalı HEAD: `ad061591`. **E01** run 9: komut edilen 5,0 mm; kullanıcı `observe(true)` #1131 ve kontrolcü `PASSED_USER` #1133. **E02** run 10: komut edilen 10,0 mm, kullanıcı tarafından girilen ölçüm 10,0 mm #1235, `observe(true)` #1249, `PASSED_USER` #1251, hesaplanan fark 0,0 mm; bağımsız otomatik uzunluk ölçümü iddia edilmez. **E07** run 12: komut edilen 5,0 mm, `observe(true)` #1360, `PASSED_USER` #1362. Üçünde de kanıtta `modal_restore_verified=true` mevcut, ancak kontrolcünün `restore_verified=false` sonucu korunmuştur; tüm fiziksel durumların geri yüklendiği iddia edilmez. E01'in eski preheat `BLOCKED` run 6 (#971) kaydı geçmişte korundu. **E03** run 7/8/11 (#1015/#1040/#1281), **E11** run 13 (#1392) ve koşullu **E12** run 14 (#1420) `BLOCKED / motion_requires_cold_idle_heaters` durumunda kaldı; kabul veya uydurma sensör geçişi eklenmedi. Daha önce kabul edilen S15/S16/S17 kayıtları değişmedi. **Güncel toplam: 62 kayıt / 46 ID — 54 KABUL, 2 BEKLİYOR, 5 KOŞULLU, 1 N/A.**

## 18 Ekim 2026 — Elle MMU kapatma isteyen testler askıya alındı

Kullanıcı tasarım kararıyla **E11 ve E12 çalıştırılabilir Maintenance testleri arasından çıkarıldı**. Eski E11 akışı MMU'nun elle kapatılmasını ve filament parçalarının elle takılıp çıkarılmasını istiyordu; güvenli otomatik geçiş ve MMU'nun özgün durumuna doğrulanmış dönüş uygulanmamıştı. E12'nin eski firmware durum okumaları da tüm mekanik işlemlerin kapsamlı testini kanıtlamıyordu. Test adaptörlerinin kayıtları ve doğrudan başlatma yetkisi kaldırıldı; donanım keşfi/katalog ve önceki `BLOCKED` trace korunuyor. E11 hâlâ **BEKLİYOR**, E12 **KOŞULLU**; yeni fiziksel kabul verilmedi. İleride hiçbir test kullanıcıdan alt sistemi elle açıp kapatmasını istemeyecek; güvenli otomatik geçiş ve doğrulanmış özgün duruma dönüş zorunludur. Toplam değişmedi: **54 KABUL, 2 BEKLİYOR, 5 KOŞULLU, 1 N/A**.

## 18 Ekim 2026 — E03 kullanıcı gözlemiyle fiziksel kabul

Kullanıcı referans yazıcıdaki E03 filament var/yok sensörü testinin olması gerektiği gibi çalıştığını açıkça doğruladı ve kabulünü istedi. `filament_switch_sensor mmu_gate_sensor` hedefi **KABUL** edildi; sonuç `OBSERVED_USER` (yalnız kullanıcı gözlemi) olarak kaydedildi. Doğrulanmamış bir firmware `PASSED` sonucu yazılmadı. Yeni trace paylaşılmadı; yok → var → yok geçişlerinin ayrı sensör okumaları, son ekran/kontrolcü çıktısı ve sensörün özgün etkin durumuna dönüşü bağımsız doğrulanmadı (`restore_verified=false`). Önceki E03 `motion_requires_cold_idle_heaters` BLOCKED denemeleri (#1015/#1040/#1281) tarihçede aynen korundu. E11 bekleyen/askıda, E12 koşullu/askıda. **Güncel toplam: 62 kayıt / 46 ID — 55 KABUL, 1 BEKLİYOR, 5 KOŞULLU, 1 N/A.**
