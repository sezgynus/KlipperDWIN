# Maintenance rezonans

[English](maintenance-resonance.md)

R01 keşfedilen doğru çipi sorgular ve gerçek ivme vektörünü doğrular. R03 yalnız sensöre atanmış eksenlerin gürültüsünü ayrıştırır. Bir sensör birkaç eksene hizmet ediyorsa R02/R04 açık eksen seçimi sunar. Desteklenmeyen eksenler görünmez.

R02 benzersiz dosya adıyla Klipper TEST_RESONANCES çalıştırır ve gerçek PSD CSV'sini mevcut worker üzerinde ayrıştırır. Yerel sonuç dosyası aktarımı için aynı host üzerindeki Moonraker gerekir; erişilemeyen, eski, bozuk, ilgisiz veya aşırı büyük dosya PASS üretmez. R04 hem ölçülmüş öneriyi hem eşleşen bekleyen input-shaper konfigürasyonunu doğrular. Canlı input shaping değişebilir; SAVE_CONFIG gönderilmez.

İsteğe bağlı beyan: ~/.config/Petrel/maintenance-resonance.json:
```json
{"version":1,"mount_id":"toolhead-fixed-v1","belt_test":false}
```
R02 sonrasında istenirse montaj referansı açık eylemle kaydedilir. R05 uyumlu frekans gridlerini ve tepe kaymasını bu referansla karşılaştırır; belirli arıza teşhisi koymaz. Sensör taşındığında mount_id değiştirilmeli. Referanslar sınırlı, atomik ve konfigürasyon/firmware'e özgüdür. Keşif kaydedilen yeteneği sonraki Klipper READY epoch'unda görür.

belt_test true ve CoreXY/CoreXZ geometrisinde R06, ayrı ayrı onaylanan iki çapraz ölçüm yapar; tepe frekanslarını ve oranını gösterir, Newton cinsinden kayış gerilimi üretmez. Yapılandırılmış bütün rezonans noktalarını ve çapraz hareket yollarını açık tutun. Firmware limitleri ve doğal input-shaper geri yüklemesi korunur.

Kullanıcı seçimlerinin süresi dolmaz. Her dispatch kuyruk/bağlantı güvenliğini yeniler; belirsiz hareketin iptali tekrar gönderimsiz Klipper emergency_stop kullanır. CI fiziksel kabul değildir.
