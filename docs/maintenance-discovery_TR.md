# Maintenance yetenek keşfi (geliştirme)

[English](maintenance-discovery.md) · [Türkçe](maintenance-discovery_TR.md)

**Durum:** Bu keşif modülü Klipper READY bağlantı döneminde bir kez çalışır ve pasif kalır. Ayrı [Aşama 8 Maintenance motoru](maintenance-stage8-acceptance_TR.md) artık güvenlik kontrollü, açık izinli fiziksel testler sunar; keşif kendi başına test başlatmaz.

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

## Uygulanan yetenek kapsamı

Keşif uygulaması; yapılandırılmış ısıtıcıları, yaygın Klipper fan türlerini, fiziksel endstop adaylarını, hareket/step motor tanımlarını, TMC'nin doğrulanabilen kısıtlı alanlarını, standart ve load-cell probe seçeneklerini, manuel ve otomatik bed-mesh ön koşullarını, ivmeölçer/rezonans ön koşullarını, filament sensörlerini, sınırlı sayıda çevresel sensör ve LED'i, ayrıca API ile doğrulanmış host/servis yeteneklerini kapsar.

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

Klipper'ın `bme280`, `htu21d`, `sht3x` ve `aht10` sensör nesneleri, Petrel'in canlı aboneliğinden bağımsız olarak çevresel durum alanlarını destekler. **Yetenek** READY anında keşfedilir; gerçek ölçüm yalnız ihtiyaç halinde okunur. `bme280` nesnesi yalnız basınç ölçen BMP280 de olabilir: basınç ekranı geçerlidir, nem gerektiren işlevler için ek olumlu kanıt aranır.

### TMC sıcaklık monitörleri: tek seferlik yapılandırılmış API kanıtı

Her Klipper READY döneminde mevcut read worker, sınırlı Moonraker servis sorgularına ek olarak bir kez salt okunur `GET /printer/objects/query?heaters=available_monitors` isteği yapar. Klipper sürücü devre dışıyken canlı `temperature` alanı `null` olsa bile sıcaklık monitörü sağlayan sürücüleri listeler. Yalnızca tanınan TMC nesneleri küçük olumlu kanıt etiketlerine çevrilir (en fazla 64); API yanıtları ve ham nesneler atılır. Sürücü etkinleştirilmez, G-code gönderilmez, abonelik eklenmez. Gerçek test başladığında güncel ölçüm ayrıca doğrulanır.

Tanınan Klipper TMC nesnelerinde belgelenen yapılandırılmış `drv_status` alanı, motor devre dışıyken `null` olabilir. Bu nedenle yalnız M07, açılışta başarılı test değil tanılama **yeteneği** olarak keşfedilir. M10 numarası ayrılmıştır, keşfedilmez. Gerçek hata değerlendirmesi güncel ve `null` olmayan durumla sürücüye özel bit çözümlemesi gerektirir. Keşif sırasında `DUMP_TMC` gönderilmez; sürücü sıcaklığı yalnız `heaters.available_monitors` ile belirlenir.

CI artık tam regresyon paketinin yanında sentetik 150 fanlık Maintenance keşfinin süresini, Python tahsislerini ve mevcutsa Linux RSS/PSS/USS değerlerini de raporlar. GitHub runner sonuçları erken regresyon göstergesidir; **Pi Zero 2 W kabul ölçümünün yerine geçmez**. Master'a birleşmeden önce gerçek Petrel process'inde önce/sonra karşılaştırması gereklidir.

**Benchmark yorumlama:** RSS/PSS/USS için enstrümansız process, Python tahsisleri için ayrı `--trace` process çalıştırılır. İzleme mekanizması RSS'yi ciddi biçimde artırabilir; izlemeli RSS **üretim ortamındaki tüketim değildir**. Her iki GitHub runner ölçümü de gerçek Pi Zero 2 W üzerindeki Petrel process karşılaştırmasının yerine geçmez. Değişmez snapshot'ın yaklaşık boyutu ayrıca raporlanır.

### Sınırlı başlangıç kanıtı ve bellek temizliği

READY keşfi yalnız beş küçük belgelenmiş API uç noktasını sorgular (`/server/info`, `/machine/proc_stats`, `/server/history/totals`, `/printer/objects/query?heaters=available_monitors`, `/server/files/roots`). Kullanılmayan, büyük olabilen `/machine/system_info` isteği kaldırıldı. Her JSON yanıtı kısa kanıt etiketlerine çevrilir ve **bir sonraki sorgudan önce** bırakılır; tam API yanıtlarının bir listesi veya sözlüğü tutulmaz. Disk alanı keşif sırasında tahmin edilmez, gerektiğinde sorgulanır.

### Dinamik menü listesi ve rezonans eksenleri

`available_features()` ve cihaz adı verilmeden çağrılan `method(feature)`, cihazlara ait maskelerle genel yetenekleri birlikte hesaplar. Cihazlar `instances(feature)` ile ayrı listelenir. Rezonans işlevlerinde `snapshot.axes('R02'|'R03'|'R04', device=None)`, Klipper'ın ortak XY veya ayrı accel_chip_x/accel_chip_y/accel_chip_z tanımlarına uygun X/Y/Z bit maskesi (1/2/4) verir; atanmamış eksen ölçülebilir gösterilmez. Kalıcı özellik sözlüğü veya indeks oluşturulmaz.

Depolama S04 artık küçük `GET /server/files/roots` yanıtında okunabilir `gcodes` kökü varsa keşfedilir. Moonraker, `disk_usage` alanını `GET /server/files/directory?path=gcodes` yanıtında sunar; çok sayıda dosya içerebilecek bu dizin sorgusu **READY anında asla yapılmaz**. Gerçek boş/toplam alan sonraki depolama ekranında gerektiğinde okunabilir. Kökün varlığı ölçülen boş alanı değil, yöntem desteğini kanıtlar. READY keşfinde beş salt-okunur API isteği vardır. <https://moonraker.readthedocs.io/en/latest/external_api/file_manager/>

### Gerçek Pi Zero 2 W kabul ölçümü (merge öncesi zorunlu)

Sentetik Python tahsisleri yerine çalışan Petrel process'ini ölçmek için `tools/measure_petrel_resources.py` kullanılır. Aynı yazıcı yapılandırmasıyla Pi'ye **master** kurulup Klipper READY olduktan sonra, kontrollü boşta veya eşdeğer baskı yükünde servis process'i ölçülür:

```sh
PID=$(systemctl show -p MainPID --value Petrel.service)
python3 tools/measure_petrel_resources.py capture --pid "$PID" --seconds 30 --output /tmp/petrel-master.json
```

Aynı cihazda ve eşdeğer yükte feature branch kurulup çıktı `/tmp/petrel-feature.json` olarak kaydedilir; ardından:

```sh
python3 tools/measure_petrel_resources.py compare --baseline /tmp/petrel-master.json --candidate /tmp/petrel-feature.json --max-uss-kib 1024 --max-rss-kib 1024
```

Araç yalnız kullanıcı çalıştırdığında devreye giren, standart Python kütüphanesini kullanan **haricî ölçücüdür**. Linux `/proc/<pid>/smaps_rollup` ve CPU tick'lerini okur; Petrel'e debugger bağlamaz, G-code göndermez veya arka plan servisi kurmaz. Medyan RSS/PSS/USS farkını ve tek çekirdek CPU kullanımını karşılaştırır. PASS hem medyan RSS hem USS artışının limitleri aşmamasını gerektirir ve yalnızca benzer iş yükleri için geçerlidir; geliştirme dalında fiziksel Pi ölçümü yapılmış değildir. Hem boşta hem aynı baskı senaryosunda kontrol ve Klipper READY sırasındaki başlangıç bellek tepesi ayrıca gereklidir.

### Yapılandırılmış step motorlar her zaman ayrı Klipper durum nesnesi değildir

Etkin `configfile.settings`, `printer.objects.list` içinde aynı adlar ayrı durum nesneleri olarak bulunmasa bile `stepper_x/y/z` ve numaralı varyantları için yetkili kaynaktır. Maintenance artık yalnız bu tanınmış **etkin yapılandırma bölümlerini** geçici keşif adaylarına ekler ve sonuçta yalnız sıkıştırılmış cihaz yeteneklerini tutar. Böylece ek durum aboneliği veya G-code olmadan M04/M05/M06 motor ve M01 fiziksel endstop yetenekleri keşfedilir. Numaralı yardımcı Z motorlarında bağımsız G1 seyahat/mesafe testi sunulmaz; yalnız kaba `STEPPER_BUZZ` desteği vardır. P06, sanal olmayan fiziksel Z-endstop pini gerektirir.

### İvmeölçer ve rezonans testinde etkin yapılandırma kanıtı

Klipper `printer.objects.list` yalnız `get_status()` metodu olan nesneleri listeler. ADXL345 gibi sürücüler ve `ResonanceTester` bu metodu sağlamadığında, geçerli ve çalışan yapılandırmaya rağmen listede görünmeyebilir. Maintenance artık etkin `configfile.settings` içindeki `adxl345`, `lis2dw` ve diğer desteklenen ivmeölçer bölümlerini (adlandırılmış varyantlarla) ve `resonance_tester` bölümünü tanır. R02/R03/R04 için ivmeölçer-eksen atamasını doğrular. Yalnız `adxl_power` adlı bir pin bulunması sensör kanıtı **değildir**. Gerçek sensör verisi ve başarılı ölçüm test sırasında ayrıca doğrulanır; keşifte sensöre enerji verilmez.

### Gerçek Petrel process'inde yaşam döngüsü kabul testi

Petrel servisi, yapılandırma değerlerini ve cihaz adlarını yazmadan, yalnızca **üç sınırlı INFO olayı** üretir: `Maintenance discovery: READY epoch=N devices=X features=Y` (ilk yapısal snapshot), `Maintenance discovery: EVIDENCE epoch=N services=S devices=X features=Y` (aynı READY için API kanıtlarının tek sefer tamamlanması) ve `Maintenance discovery: CLEAR epoch=N` (bağlantı kesilmesi veya kapanış). Bunlar menüye girişte veya olağan telemetri değişiminde çalışmaz; yeni abonelik, G-code veya arka plan işi oluşturmaz. Yazıcı boşta iken `sudo journalctl -u Petrel.service -f -o cat | grep --line-buffered 'Maintenance discovery:'` ile günlükleri izle; READY/EVIDENCE için önce **yalnız Petrel'i** yeniden başlat, Maintenance menüsüne üç kez girip çık (yeni olay olmamalı), sonra **yalnız Moonraker'ı** yeniden başlat (CLEAR ve yeni epoch içinde READY/EVIDENCE beklenir). Baskı sırasında servis yeniden başlatma. Bu gözlemsel kayıt fiziksel sensör başarısını veya bağımsız test sonucunu kanıtlamaz.
