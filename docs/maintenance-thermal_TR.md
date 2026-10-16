# Termal Maintenance
H11 (raporlanan görev oranı), H14 (sensör sıcaklığı) ve H16 (çevre verisi),
kullanıcı isteğiyle cihaz bazında çalışan Diagnostics okumalarıdır. Ortak sınırlı
worker ve taze kuyruk/oturum kontrolleri kullanılır. Klipper eventtime eklenir;
eksik/sonlu olmayan alanlar sonuçsuzdur. Görev oranı elektriksel güç ölçümü değildir.
Donanım PASS veya fiziksel kabul üretilmez. Başlangıçta polling yapılmaz.
Fiziksel H testleri ve kalibrasyon, bağımsız termal güvenlik controller'ı kurulana
kadar kullanılamaz. Mevcut kabul kayıtları değişmez.

## Ölçüm sözleşmesi
H01/H05/H06/H07/H08/H09/H13 en çok 256 Klipper-eventtime örneğinde ayrı
değerlendirilir. Tekrarlanan zaman, 5 sn üzeri boşluk ve sonlu olmayan veri
reddedilir. H01/H13 en az 5 C artış; H05 pozitif ortalama ısıtma eğimi;
H06 hedef eksi 1 C'ye erişme; H07 en çok 5 C aşım; H08 20 sn yerleşme
sonrasında en az 30 sn boyunca en çok 2 C tepeden tepeye değişim;
H09 en az 30 sn negatif soğuma eğimi ister. Bunlar sınırlı tanılama
ölçütleridir; fabrika performans şartı veya bağımsız termal güvenlik kanıtı değildir.
Standart başlangıç hedefleri hotend 60 C / yatak 45 C, süre 120 sn ve
yapılandırılmış max_temp altında kalması gereken hedef+10 C gözlem sınırıdır.
Yapılandırılmış bütün ısıtıcılar sıfır hedef ve sıfır görev oranıyla başlamalıdır.
Genel ısıtıcılar açık uygulama profili gerektirir; hazne sıcaklığı tahmin edilmez.
Salt derleyici, süreli bekleme sonrasına OFF ekler. SAVE_CONFIG yoktur.
