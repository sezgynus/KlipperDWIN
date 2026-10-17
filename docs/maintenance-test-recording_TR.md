# Geçici fiziksel test kaydı

Bu araç yalnızca Maintenance fiziksel kabul çalışması içindir. Normal test menülerini kullanır; test çalıştırmaz, güvenliği değiştirmez, otomatik PASS/kabul vermez.

## Kullanım

1. Maintenance → **Start test recording**.
2. Self Tests veya Diagnostics listesinden testleri sırayla çalıştırın.
3. Soruları cevaplayın ve istenen gerçek ölçümleri ekrandan girin. Bu cevaplar da kaydedilir.
4. Bir sorun oluşursa tekrar tekrar denemeden sonraki teste geçebilir veya sonucu not edebilirsiniz. Test aktifse mevcut güvenli bitirme/iptal akışını kullanın.
5. İşiniz bittiğinde Maintenance → **Stop test recording**.
6. [Remote Display](http://openeye3dpi.local:8088/) içindeki **Download test recording** bağlantısından tek ZIP indirin; dosyayı sohbete ekleyin.

Genel adres: `http://<petrel-host>:8088/maintenance-test-trace.zip`.
Mevcut Diagnostics S20 sonucu ile bu ayrıntılı kayıt farklıdır; S20 çalıştırmanız gerekmez.
Kayıt başlatmak/durdurmak donanım testi başlatmaz. Aktif test veya okuma varken kayıt kapatma isteği reddedilir; test iptal edilmez.

## Kaydedilenler

- UTC/monotonik zaman, oturum ve deneme kimliği, test/cihaz/yöntem/READY epoch bilgileri.
- Çalışan git HEAD ve başlangıç config özeti SHA-256; config içeriği kaydedilmez.
- Test başlangıcı, onay, seçim, gözlem, ölçüm girişi, iptal; geri dönüş değeri ve aşama geçişleri.
- Mevcut Maintenance GET yanıtlarından izinli sıcaklık/hedef/güç, konum, sensör, kuyruk ve benzeri değerler. Ek Moonraker sorgusu yapılmaz.
- Komut adları ve sayısal parametreleri, script özeti, RPC tamamlanması/hatası. RPC başarısı fiziksel PASS değildir.
- Shutdown isteğinden **önce** teknik neden ve son ölçüm; sonuç/restore kanıtı.
- UI girişinden önce/sonra ekran, sayfa, seçili satır ve yazısı, yakın satırlar, dönüş menüsü ve test aşaması.
- Periyodik UI geçişleri ve recovery gibi başka ekran açıkken hâlâ aktif test bulunması.
- Firmware cevaplarının ham metni, tam config, dosya adları, URL ve kimlik bilgileri kaydedilmez.

Bir testin sonucu yoksa tamamlandığı varsayılmaz. Fiziksel gözlem ekrandaki cevabınızdır; ekranda ifade edilemeyen bir durumu ayrıca yazın.

## Süreklilik ve sınırlar

Kayıt varsayılan olarak kapalıdır. **Petrel servisi yeniden başlarsa yeniden Start test recording seçin.** Klipper yeniden başlatılırken aynı Petrel süreci çalışıyorsa kayıt oturumu devam eder.
Önceki diske yazılmış kayıtlar servis yeniden başlatıldığında silinmez. Her yeni başlangıç ayrı oturumdur.
Elektrik kesilirse henüz diske yazılmamış kuyruk kaybolabilir; normal yazma yaklaşık saniyeliktir, mevcut worker yoğunluğunda gecikebilir.

En fazla 128 bekleyen olay (olay başına 8 KiB), diskte iki adet 4 MiB JSONL tutulur. Eski kayıtlar döndürülür; uzun çalışmalarda ara ZIP indirin.
Taşma/yazma hataları menüde `(gaps)` ve ZIP manifestindeki sayaçlarla belirtilir. GET indirmesi bekleyen kuyruğu da içerir; kayıtları temizlemez veya test komutu üretmez.
Kaydın diske yazılması mevcut **ayrı okuma worker'ı** üzerindedir; Maintenance güvenlik okuma kuyruğuna disk işi eklenmez. Yeni thread açılmaz.
Gözlem/seçim beklerken timeout eklenmez.

ZIP: `events.previous.jsonl`, `events.jsonl`, `pending.jsonl`, `manifest.json`, `README.txt`.
Kayıtları bu sırayla, ardından session/run/seq ile değerlendirin. Döndürme nedeniyle eski başlangıç eksikse kabul çıkarmayın.

## Kolay kaldırma

Kalıcı kontrolcü değişikliği yoktur. Kaydı durdurunca özgün owner/client/worker referansları geri yüklenir.
Kodun tamamını kaldırmak için:

- `maintenance_test_trace.py` ve `tests/test_maintenance_test_trace.py` dosyalarını kaldırın.
- `printerInterface.py`, `ui_maintenance.py`, `petrel_ui.py` içindeki **TEMPORARY MAINTENANCE TEST TRACE** işaretli bağlantıları kaldırın; UI sarmalayıcılarını özgün yöntem adlarına geri taşıyın.
- Remote Display'deki `trace_provider`, ZIP endpoint ve indirme bağlantısını kaldırın.
- Bu TR/EN rehber çiftini kaldırın.

Kayıt verileri yalnızca `~/.config/Petrel/maintenance-test-trace/` dizinindedir. Arşivi aldıktan ve Petrel durdurulduktan sonra yalnızca bu dizin silinebilir; kalıcı Maintenance history/usage/acceptance dosyalarına dokunulmaz.
