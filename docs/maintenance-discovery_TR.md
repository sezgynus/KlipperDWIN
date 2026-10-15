# Maintenance yetenek keşfi (geliştirme)

[English](maintenance-discovery.md) · [Türkçe](maintenance-discovery_TR.md)

**Durum:** Keşif, Klipper yapılandırmasının her READY bağlantı döneminde bir kez çalışır. Fiziksel test yürütme etkin değildir; snapshot bir test yürütücüsü değildir.

## Tasarım sınırları

- `maintenance_discovery.py`, mevcut `printer_capabilities.py` dosyasından bağımsızdır. Maintenance geliştirmesi mevcut yetenek sınıfını değiştirmez.
- `discover(state, services=())`, Klipper/Moonraker aboneliğinden zaten alınmış `PrinterState` verilerini salt okunur şekilde kullanır. **G-code göndermez**, keşif için HTTP isteği oluşturmaz, yapılandırma sözlüklerini kopyalamaz, giriş durumuna referans saklamaz, thread veya soket açmaz.
- Moonraker/Petrel servisleri yalnızca çağıranın sunduğu **olumlu API kanıtıyla** etkinleştirilir. Doğrulanmayan servis mevcut sayılmaz.
- Sonuç, bir testin **yöntemini** tarif eder; başarılı sağlık testi veya komut yürütme izni değildir. Çalıştırma katmanı baskısız durum, cihaz sınırları, bağlantı epoch'u, aktüatör güvenliği ve kullanıcı onayını ayrıca denetleyecektir.
- Makro adlarından, keyfî çıkış pinlerinden veya yalnızca `ok` döndüren komutlardan başarı çıkarılmaz. Anlamlı doğrulama yoksa test gizli kalır.
- Kalıcı sonuçlarda yalnızca değişmez epoch, cihaz adı/türü, sıkıştırılmış tamsayı yöntem maskesi ve genel yöntem maskesi tutulur. API yanıtı, ayar/durum sözlüğü veya örnekleme geçmişi tutulmaz.
- Keşif her epoch için ilk Klipper READY güncellemesinde çalışır; Maintenance menüsüne girerken veya olağan baskı durum güncellemelerinde yeniden çalışmaz.

## READY dönemi snapshot yöneticisi

`maintenance_cache.py`, `MaintenanceCache.get(state, services=())` arayüzünü sağlar. İlk READY döneminde keşif modülünü yükler. Klipper epoch’u, etkin ayar nesnesinin kimliği ve olumlu doğrulanmış servis kümesi aynıysa **aynı** değişmez snapshot döndürülür; yeni yapılandırma/epoch veya servis kümesi değişirse yeniden hesaplanır. Bağlantı kopmuş durum snapshot’ı temizler. Cache yalnızca sonuç nesnesini tutar, kaynak durumu saklamaz. Snapshot READY dönemi boyunca backend içinde korunur. Menüye girip çıkmak keşif yapmaz; bağlantı kesilince sonuç geçersiz kılınır.

## Yöntem bayrakları

| Bayrak | Anlamı |
|---|---|
| `AUTOMATIC` | Gerçek firmware/sensör geri bildirimi kullanılabilir |
| `USER` | Kullanıcı tarafından doğrudan ve anlamlı şekilde gözlenebilir |
| `EXTERNAL` | Gerçek ölçü aleti ve sayısal kullanıcı girişi gerektirir |
| `CALIBRATION` | Klipper tarafından desteklenen yönlendirmeli kalibrasyon |
| `INFORMATION` | Bilgi/tahmin/geçmiş; **fonksiyonellik kanıtı değildir** |
| `NONE` | Yeterli kanıt yok; gizli |

Bayraklar birleşebilir. 121 standart ID'nin (`F01–F13`, `H01–H18`, `M01–M17`, `P01–P22`, `R01–R08`, `E01–E15`, `S01–S20`, `O01–O08`) her biri sıkıştırılmış maskede beş bit kullanır. Henüz uygulanmayan veya kanıtlanmayan ID sıfır kalır.

`MaintenanceSnapshot.method(feature, device=None)`, tek bir cihaz veya genel özellik için bayrakları döndürür. `instances(feature)` ilgili cihazları seçer. Nesneler değişmezdir; kalıcı özellik sözlükleri oluşturulmaz.

## İlk keşif aşaması

İlk sürüm; yapılandırılmış ısıtıcıları, yaygın Klipper fan türlerini, fiziksel endstop adaylarını, hareket/step motor tanımlarını, TMC'nin doğrulanabilen kısıtlı alanlarını, standart ve load-cell probe seçeneklerini, manuel ve otomatik bed-mesh ön koşullarını, ivmeölçer/rezonans ön koşullarını, filament sensörlerini, sınırlı sayıda çevresel sensör ve LED'i, ayrıca API ile doğrulanmış host/servis yeteneklerini kapsar.

**Henüz otomatik desteklendiği iddia edilmeyenler:** Kanıtı bulunmayan TMC kayıtları, geçmiş referansı olmadan ileri trend analizleri, bilinmeyen aktüatör işlevleri, rastgele G-code makroları, keyfî servo hareketleri, yapılandırılmamış tanılama entegrasyonları ve sensör yanıtlarına yapılandırılmış API ile erişilemeyen testler. Adaptör ve kanıt politikaları eklenene kadar ilgili ID'ler gizli kalır.

Fan `tachometer_pin`, otomatik RPM doğrulama ihtimalini gösterir. Test çalıştırıcısı gerçek RPM alanına abone olmalı ve PASS kaydından önce örnekleri doğrulamalıdır. Heater/controller fan testleri Klipper'ın otomatik güvenlik mantığını devre dışı bırakmamalıdır. Hareket telemetrisi fiziksel konum geri bildirimi değildir.

## Performans testleri

```sh
python3 -m unittest discover -s tests -p 'test_maintenance_discovery.py' -v
python3 tools/benchmark_maintenance_discovery.py --fans 150 --runs 20
```

Benchmark; keşif süresi, `tracemalloc` kalıcı tahsis farkı, en yüksek izlenen tahsis ve Linux `/proc/self/smaps_rollup` RSS/PSS/USS değişimini raporlar. Ölçümler **sentetik ve ortama bağlıdır**: Aynı testi Pi Zero 2 W'de çalıştırmak ve UI entegrasyonundan önce/sonra **gerçek Petrel process'ini** karşılaştırmak gerekir. Python tahsis testinin geçmesi, CPython'un bütün belleği işletim sistemine iade edeceğini garanti etmez.

**Kabul hedefi, ölçülmüş garanti değil:** Yeni kalıcı worker/soket/polling yok; gerçekçi cihaz envanteri için 100 KiB altında kalıcı snapshot; baskının sıcak kod yolunda keşif yok; Klipper READY sonrasında ilave kararlı RSS için 1 MiB altı hedef. Ölçüm hedefi aşarsa işlevi etkinleştirmeden önce mimari gözden geçirilir.

## Sonraki aşamalar

1. Kalan tanınabilir test adaptörlerini doğrulanmış API kanıtları ve ayrı regresyon testleriyle tamamla.
2. Snapshot'ı Maintenance ziyaretleri arasında backend'de koru; yalnız yeni Klipper READY döneminde yeniden keşfet.
3. Moonraker servis kanıtını READY döneminde bir kez al; ek test telemetrisine yalnız kullanıcı test başlattığında abone ol.
4. Test yürütme/güvenlik koordinasyonunu keşiften bağımsız tasarla; UI'yi keşif matrisi doğrulandıktan sonra oluştur.

## Genişletilmiş API tabanlı keşif ve 121 kimliğin tamamı

Tamamlanan keşif **karar motoru**, 121 özellik kimliğinin tamamına ait
koşul sözleşmesini tanır. Bu, 121 işlevin de görüntüleneceği anlamına gelmez:
desteklenmeyen, güvenli olmayan veya ölçülemeyen testler bilinçli olarak
gizlenir (`NONE`). Özellikle `M02`, `M17`, `R07`, `R08`, `E10`, `O07` ve `O08`
için genel geçerli bir ölçüm yöntemi bulunmuyor. Tarihsel eğilimler, özel
aktüatörler, hareket mesafesi sayaçları ve MMU testleri açıkça doğrulanmış
entegrasyon, geçmiş referansı veya güvenli çalışma profili gerektirir; isimden
yetenek uydurulmaz.

| Alan | Görünürlük koşulu |
|---|---|
| Fanlar | Her Klipper fanı ayrı keşfedilir. RPM testi için takometre pini gerekir; basit PWM fanında anlamlı kullanıcı doğrulaması korunur. Otomatik fan kontrolü zorla bypass edilmez. |
| Termal | Hotend, tabla ve generic heater ayrı ve geçerli limitlerle keşfedilir. Trend ve enerji tahmini için doğrulanmış ek kayıt gerekir. |
| Hareket | Bas/bırak testinde gerçek fiziksel anahtar gerekir. TMC kayıt/sıcaklık/akım özellikleri yapılandırılmış veriyle doğrulanır. Komut edilmiş pozisyondan mikron doğruluk çıkarılmaz. |
| Probe / mesh | Load-cell ve eddy probe ayrı yöntemlerle; manuel ve otomatik mesh ayrı koşullarla keşfedilir. Tarihsel kayma için uyumlu referans gerekir. |
| Rezonans | Salt ivmeölçer varlığı yetmez; `[resonance_tester]` içinde ilgili sensör atanmış olmalıdır. İnsan tahmini frekans ölçümü sayılmaz. |
| Filament / MMU | Presence/motion sensörleri ayrıdır; güvenli profili bulunmayan servo, makro ve aktüatörler otomatik teste dönüşmez. |
| Host | Yalnızca doğrulanmış Moonraker API cevapları. Hayalî disk API'si veya büyük dosya listesi keşif sırasında kullanılmaz. |

### Yalnızca READY döneminde servis kanıtı

`maintenance_services.parse_evidence(responses)` doğrulanmış Moonraker JSON
cevaplarını sınıflandırır. `probe(client, cancelled)` Klipper READY olduğunda bir kez
çağrıldığında `/server/info`, `/machine/proc_stats`,
`/machine/system_info` ve `/server/history/totals` için küçük salt-okunur
istekler yapar. Mevcut HTTP transport ve read worker yeniden kullanılır;
baskı döngüsünde yeni bağlantı veya keşif sorgusu yoktur. Opsiyonel API
hataları yetenek üretmez. `MaintenanceDiscoveryManager` yalnızca küçük değişmez snapshot'ı, kilidi ve
bağlantı nesil bilgisini tutar. Mevcut bakım worker'ı kısa servis sorgusunu bir kez
yapar; yanıt yalnız doğru READY dönemine aitse yayınlanır. Menü giriş ve çıkışında
API isteği veya yeniden keşif gerçekleştirilmez.

Diğer `maintenance.*` ve `petrel.*` etiketleri, **gelecekte bağımsız olarak
doğrulanmış entegrasyonların** olumlu kanıt sözleşmesidir. Henüz var olmayan
referans kayıtları, aktüatör güvenlik profilleri veya sayaçlar varmış gibi
gösterilmez; bu kanıt gelene kadar özellik gizlidir.

### Performans ve entegrasyon sınırı

Modül Klipper READY olduğunda backend tarafından yüklenir. Mevcut `PrinterCapabilities`
değişmez. Normal baskı işleme döngüsüne özellik kontrolü eklenmez ve menüden
çıkınca snapshot korunur. Kesin kaynak tüketimi iddiası için gerçek Pi Zero
2 W üzerinde CPU, RSS, USS ve PSS ölçümü gerekir; sentetik benchmark ve birim
testleri fiziksel doğrulamanın yerine geçmez.

### READY anındaki statik yetenek ve test anındaki ölçüm ayrımı

Klipper READY durumunda oluşturulan sıkıştırılmış snapshot, anlık cihaz sağlığını değil **yapısal yetenekleri** kaydeder. Açılışta etkin mesh bulunmasa da yapılandırılmış `bed_mesh`, sonradan kalibrasyonla oluşturulan mesh'in incelenmesini destekler. `load_cell_probe`, ilk ölçüm henüz alınmamış olsa da Klipper sözleşmesinde kuvvet telemetrisi sağlar. `temperature_fan` sıcaklık durumunu sunar. Açıkça güvenli olarak tanımlanmış `gcode_button` durum alanı da keşif sırasında abone olunmadan test zamanında okunabilir. Bu yeteneklerin başarılı sayılabilmesi için **test sırasında güncel ve doğrulanmış API ölçümü** gereklidir. Sürekli telemetri aboneliği eklenmez; desteklenmeyen testler gizlenir.
