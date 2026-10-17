# Maintenance rezonans

[English](maintenance-resonance.md)

R01 keşfedilen doğru çipi sorgular ve gerçek ivme vektörünü doğrular. R03 yalnız sensöre atanmış eksenlerin gürültüsünü ayrıştırır. Bir sensör birkaç eksene hizmet ediyorsa R02/R04 açık eksen seçimi sunar. Desteklenmeyen eksenler görünmez.

R02 benzersiz dosya adıyla Klipper TEST_RESONANCES çalıştırır ve gerçek PSD CSV'sini mevcut worker üzerinde doğrular. Sonuç yalnızca Klipper'ın ölçüm verilerini kaydettiğini bildirir: Petrel mekanik rezonansın iyi/kötü olduğuna karar vermez, kendi bulduğu PSD tepe frekansını input-shaper önerisi gibi göstermez. Dahili tepe değeri yalnız kullanıcının açıkça seçtiği R05 eğilim/referans karşılaştırması için korunur. Yerel sonuç dosyası aktarımı için aynı host üzerindeki Moonraker gerekir; erişilemeyen, eski, bozuk, ilgisiz veya aşırı büyük dosya PASS üretmez. Gerçek input-shaper önerisi için ayrı onayla **R04** çalıştırılır: Klipper'ın kendi SHAPER_CALIBRATE komutu kullanılır, Klipper'ın önerdiği shaper türü ve frekansı bekleyen ayarlarla karşılaştırılarak gösterilir. Petrel shaper hesaplamaz veya seçmez. SHAPER_CALIBRATE canlı input shaping ayarını değiştirebilir; Petrel SAVE_CONFIG göndermez ve otomatik kalıcı kayıt yapmaz.

İsteğe bağlı beyan: ~/.config/Petrel/maintenance-resonance.json:
```json
{"version":1,"mount_id":"toolhead-fixed-v1","belt_test":false}
```
R02 sonrasında istenirse montaj referansı açık eylemle kaydedilir. R05 uyumlu frekans gridlerini ve tepe kaymasını bu referansla karşılaştırır; belirli arıza teşhisi koymaz. Sensör taşındığında mount_id değiştirilmeli. Referanslar sınırlı, atomik ve konfigürasyon/firmware'e özgüdür. Keşif kaydedilen yeteneği sonraki Klipper READY epoch'unda görür.

belt_test true ve CoreXY/CoreXZ geometrisinde R06, ayrı ayrı onaylanan iki çapraz ölçüm yapar; tepe frekanslarını ve oranını gösterir, Newton cinsinden kayış gerilimi üretmez. Yapılandırılmış bütün rezonans noktalarını ve çapraz hareket yollarını açık tutun. Firmware limitleri ve doğal input-shaper geri yüklemesi korunur.

Kullanıcı seçimlerinin süresi dolmaz. Her dispatch kuyruk/bağlantı güvenliğini yeniler; belirsiz hareketin iptali tekrar gönderimsiz Klipper emergency_stop kullanır. CI fiziksel kabul değildir.

## Eksik homing hazırlığı

XYZ hareketi gerektiren testlerin ilk ön kontrolünde eksenler home edilmemişse test yalnız bu nedenle sonlandırılmaz. `Home XYZ, then run test` onayından sonra ortak güvenlikli homing hazırlığı yürür; iki taze XYZ/mod okuması doğrulanınca aynı test yeni ön kontrolle otomatik devam eder. Hata/aktif iptal asıl testi başlatmaz. Bilgi/sensör okuma testleri homing yapmaz; Leveling'deki hariç tutulan özellikler bu değişiklikle Maintenance'a eklenmez. Hareket profili, soğuk/OFF ısıtıcılar, konum/açıklık ve diğer güvenlik koşulları korunur.

## R02 canlı güvenlik kaydı tanısı (18 Ekim 2026)

Gerçek yazıcıdaki R02/X oturumu `e66bd3a0a19140a482d12a85b7e89c3e`, `TEST_RESONANCES` komutunu gönderdi; ardından Petrel `workflow_runtime_safety_unknown` nedeniyle acil durdurma istedi. Son iş kuyruğu okuması shutdown'dan 21 ms önce `paused`, bekleyen iş sayısı 0 gösteriyordu. Bu okuma tek başına hangi alt güvenlik kontrolünün reddettiğini kanıtlamaz. Olası bir döngü içi yarış bulundu: çalışan testin guard'ı kuyruk yenilemesinin tamamlanmasını ikinci kez kontrol ediyor, ancak yeni yanıt henüz güvenlik durumuna aktarılmamış olabiliyordu. Bu ikinci kontrol kaldırıldı ve durumu yeniden üreten CI regresyonu eklendi. İsteğe bağlı trace artık tam `safety_reason`, kuyruk yaşı ve uygulanan `queue_refresh_unconsumed` istisnasını kaydeder. Canlı baskı, yaşam döngüsü, diğer işlem ve iş kuyruğu güvenlik kontrolleri korumalı kalır. R02/X **fiziksel kabul edilmedi**; kesin kök neden veya rezonans ölçümü iddiasından önce sonraki trace incelenecek.

## R02/X sırasında geçici Moonraker okuma hatası (18 Ekim 2026)

`001c0c5731db4ad9bc11b502534576e8` trace oturumunda imzalı `ad42ef5e` sürümü çalışıyordu. Homing tamamlandı, `TEST_RESONANCES` gönderildi. Yaklaşık 152 saniye sonra güvenlik amaçlı HTTP okuması `MoonrakerError` verdi. Son başarılı iş kuyruğu yanıtı `paused`, boştu. `read_queue_evidence` belirsiz sonuç döndürdü ve workflow bunu doğrudan `workflow_runtime_safety_changed` kabul edip `printer.emergency_stop` gönderdi. Ağ hatasının alt türü trace'te bulunmuyor. Artık yalnız çalışan hareket komutu sırasında, son doğrulanmış kuyruk okumasından itibaren en fazla 20 saniyelik sınırlı tekrar denemesi var; bu sürede yazdırma, Klipper, duraklatma, MMU ve diğer işlem güvenlik kontrollerinin tamamı canlı olarak uygulanıyor. Gerçekten güvensiz kuyruk yanıtı, canlı güvenlik ihlali veya uzamış belirsizlik hâlâ anında durdurulur. İsteğe bağlı trace, ardışık kuyruk okuma hatalarını ve yeniden deneme/süre aşımı nedenini kaydeder. Eski veriyle yeni komut gönderilmez ve fiziksel kabul işlenmez.
