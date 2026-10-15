# Maintenance yetenek keşfi (geliştirme)

[English](maintenance-discovery.md) · [Türkçe](maintenance-discovery_TR.md)

**Durum:** Yalnızca keşif çekirdeği ve birim testleri. Maintenance arayüzündeki işlemler veya yazıcı üzerinde çalıştırılacak testler henüz etkinleştirilmedi. Bu ilk uygulama aşamasıdır; nihai destek matrisi değildir.

## Tasarım sınırları

- `maintenance_discovery.py`, mevcut `printer_capabilities.py` dosyasından bağımsızdır. Maintenance geliştirmesi mevcut yetenek sınıfını değiştirmez.
- `discover(state, services=())`, Klipper/Moonraker aboneliğinden zaten alınmış `PrinterState` verilerini salt okunur şekilde kullanır. **G-code göndermez**, keşif için HTTP isteği oluşturmaz, yapılandırma sözlüklerini kopyalamaz, giriş durumuna referans saklamaz, thread veya soket açmaz.
- Moonraker/Petrel servisleri yalnızca çağıranın sunduğu **olumlu API kanıtıyla** etkinleştirilir. Doğrulanmayan servis mevcut sayılmaz.
- Sonuç, bir testin **yöntemini** tarif eder; başarılı sağlık testi veya komut yürütme izni değildir. Çalıştırma katmanı baskısız durum, cihaz sınırları, bağlantı epoch'u, aktüatör güvenliği ve kullanıcı onayını ayrıca denetleyecektir.
- Makro adlarından, keyfî çıkış pinlerinden veya yalnızca `ok` döndüren komutlardan başarı çıkarılmaz. Anlamlı doğrulama yoksa test gizli kalır.
- Kalıcı sonuçlarda yalnızca değişmez epoch, cihaz adı/türü, sıkıştırılmış tamsayı yöntem maskesi ve genel yöntem maskesi tutulur. API yanıtı, ayar/durum sözlüğü veya örnekleme geçmişi tutulmaz.
- Keşif modülü ileride Maintenance açıldığında **tembel yükleme** için tasarlanmıştır. **Henüz çalışan Petrel arayüzü tarafından import edilmez**; dolayısıyla bu aşama normal baskı kod yoluna ek işlem yüklemez.

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

**Kabul hedefi, ölçülmüş garanti değil:** Yeni kalıcı worker/soket/polling yok; gerçekçi cihaz envanteri için 100 KiB altında kalıcı snapshot; baskının sıcak kod yolunda keşif yok; Maintenance ilk kullanıldıktan sonra ilave kararlı RSS için 1 MiB altı hedef. Ölçüm hedefi aşarsa işlevi etkinleştirmeden önce mimari gözden geçirilir.

## Sonraki aşamalar

1. Kalan tanınabilir test adaptörlerini doğrulanmış API kanıtları ve ayrı regresyon testleriyle tamamla.
2. Yalnızca Maintenance'a ait küçük, tembel yüklenen snapshot yöneticisi ekle; yeni Klipper bağlantı/yapılandırma epoch'unda geçersizleştir.
3. Moonraker servis kanıtını ve yalnızca ihtiyaç halinde test telemetrisini sürekli abonelik oluşturmadan bağla.
4. Test yürütme/güvenlik koordinasyonunu keşiften bağımsız tasarla; UI'yi keşif matrisi doğrulandıktan sonra oluştur.