# Maintenance salt-okunur backend entegrasyonu

[English](maintenance-backend.md) · [Güvenlik](maintenance-runtime_TR.md)

**Aşama 6:** Mevcut Petrel backend'i yalnız ihtiyaç anında kullanılan bir `MaintenanceReadController` sahibi oldu. Açılışta, normal baskı telemetrisinde veya başka menü açılırken Maintenance sorgusu yapılmaz. İlave arka plan thread'i, Moonraker istemcisi, websocket veya DWIN çizim döngüsü yoktur.

`PrinterData.maintenance_read_plan()`, keşfi, kataloğu ve altı sabit bilgi adaptörünü (S01/S02/S03/S05/S08/S10) eşler. `start_maintenance_read(feature_id)`, sınırlı salt-okunur job queue ön kontrolünü Petrel'in mevcut Maintenance worker'ına kuyruğa alır; UI thread'de ağ isteği yapmaz. `poll_maintenance_read()`, kuyruk kanıtı hazır olduğunda asenkron Future akışını ilerletir ve beklerken sonuç döndürmez, tamamlanınca `ReadResult` verir. `cancel_maintenance_read()` eski sonuçları atar. Controller bağlantı/epoch geçişinde iptal edilir, paylaşılan worker/client kapanmadan önce kapatılır.

Ön kontrol `/server/info` ile job_queue varlığını açıkça doğrular; varsa `/server/job_queue/status` okur. Başarısız endpoint kuyruk kapalı kabul edilmez. Gerçek printer-state, print/pause/manual-probe/MMU ve diğer Petrel işlem sahipleri GET öncesi ve sonuç alınırken yeniden kontrol edilir. Salt-okunur bilgi sonuçları hiçbir zaman fiziksel PASSED olarak sunulmaz. Fiziksel aktüatör testi içermez.

**Henüz UI özelliği değildir:** LCD Maintenance ekranı değişmedi. Bu backend API sonraki Diagnostics/Information ekranları için isteğe bağlıdır. Haricî Mainsail/Fluidd komutları güvenlik kontrolleriyle yarışabilir; fiziksel testlerden önce daha güçlü komut öncesi senkronizasyon gereklidir.

`tests/test_maintenance_controller.py`, gerçek backend yapımı, kuyruk var/yok, baskı başlangıcı, eski epoch, iptal, isteğe bağlı çalışma ve UI'yi bloke etmeyen akışı tam GitHub CI içinde kapsar.
