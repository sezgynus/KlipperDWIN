# Termal Maintenance
H11 (raporlanan görev oranı), H14 (sensör sıcaklığı) ve H16 (çevre verisi),
kullanıcı isteğiyle cihaz bazında çalışan Diagnostics okumalarıdır. Ortak sınırlı
worker ve taze kuyruk/oturum kontrolleri kullanılır. Klipper eventtime eklenir;
eksik/sonlu olmayan alanlar sonuçsuzdur. Görev oranı elektriksel güç ölçümü değildir.
Donanım PASS veya fiziksel kabul üretilmez. Başlangıçta polling yapılmaz.
Fiziksel H testleri ve kalibrasyon, bağımsız termal güvenlik controller'ı kurulana
kadar kullanılamaz. Mevcut kabul kayıtları değişmez.
