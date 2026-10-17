# Sınırlı salt-okunur Maintenance yürütücüsü (geliştirme)

[English](maintenance-read-executor.md) · [Güvenlik](maintenance-safety_TR.md)

**Durum:** Bağımsız backend altyapısında yalnız bilgi sunan altı adaptör var. Motor/ısıtıcı/fan sürülmez, G-code çalıştırılmaz, Maintenance menüsü oluşturulmaz veya fiziksel PASSED sonucu verilmez.

`maintenance_executor.py`, yalnız S01, S02, S03, S05, S08 ve S10 için sabit, sınırlandırılmış GET endpoint'leri ve şemaya özel skaler alan seçicileri içerir. İstekler Petrel'in **mevcut** Moonraker istemcisi ve bounded read worker'ıyla, yalnız ihtiyaç anında yürütülür. Yeni thread, polling döngüsü, websocket aboneliği veya ağ istemcisi yoktur. Her okuma Safety Coordinator tarafından pozitif olarak doğrulanan boşta/oturum kontrolüyle başlar. Worker GET komutundan hemen önce ve Future sonucu alınırken durum yeniden kontrol edilir; eski yanıt baskı başlangıcı, kopuş veya epoch/config değişiminden sonra yayımlanamaz.

`start(row)`, açıkça tanımlı INFORMATION planını, güvenilir sabit adaptörü, sınırlı timeout'u ve güncel pozitif güvenlik bağlamını doğrulayıp kabul durumunu döndürür. `poll()` engellemez; sonuç hazır değilken `None` döndürür. `cancel()` oturumu geçersizleştirip eski yanıtı atar; `close()` Petrel'e ait istemci/worker'ı kapatmaz. Ham API sözlükleri veya gizli anahtarlar saklanmadan, yanıtın yalnız seçilmiş sayısal/durum alanları küçük kanıt tuple'ına çevrilir.

Başarılı bilgi okumasında `ReadResult.status=None` kullanılır: **telemetri gözlendi, fiziksel test PASS değildir**. Eksik ölçüm `INCONCLUSIVE`, iptal/güvensiz durum `ABORTED`, okuma hatası/zaman aşımı `ERROR` olur. Bunlar tamamlanmış fiziksel test olarak kalıcı depolanmaz.

**Entegrasyon henüz yapılmadı:** Uygulama yöneticisi bu altyapıyı mevcut worker/client ile oluşturmalı, *gerçek* kuyruk ve diğer operasyon kontrollerini sağlamalı, DWIN UI'da plan modelini kullanmalıdır. Gerçek kontrol yapılmadan SafetyContext bayrakları pozitif verilmemelidir. Bu aşama açılış iş yükü veya UI sıcak yolunu değiştirmez. TMC hata bitleri ve aktif donanım testleri, sürücüye özel kanıt ve ayrıca güvenlik onayı gerektirir.

`tests/test_maintenance_executor.py`, geçerli/eksik/geçersiz yanıtları, yöntem seçimini, iptali, sıradaki okumayı, dış baskı başlangıcını, epoch değişimini ve paylaşılan worker sahipliğini GitHub Actions CI'da kapsar.

## Güncel M07 uygulaması: homing bağımsız doğrudan register tanılaması

Yukarıdaki bölüm ilk salt-okunur GET altyapısının tarihsel kapsamını açıklar. Güncel
M07 Diagnostics, desteklenen TMC çiplerinde yalnız kullanıcının talebi üzerine
`DUMP_TMC STEPPER=<doğrulanmış isim> REGISTER=DRV_STATUS` çalıştırır.
Klipper'ın `notify_gcode_response` çıktısı mevcut Moonraker bağlantısında
komut tamamlanması ve yeni yanıt imleciyle değerlendirilir. Önceki konsol
satırları, belirsiz/çift cevap, iletişim hatası ve kayıp yanıt hatasız
sürücü sonucu üretmez. Motor enable/homing/hareket/register yazımı yoktur.
TMC2208'de doğrulanmış bit maskeleri çözülür; diğer desteklenen çiplerde
ham register gösterilir. TMC2660, yan etkili register-seçimi nedeniyle eski
pasif yolda kalır. M07 bilgi tanılamasıdır; M10 ayrılmış/boş kalır.
CI hem normal GET hem doğrudan kayıt/iletişim hata akışını sınar; yerel test yoktur.
