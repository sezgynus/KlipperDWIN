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

## Fiziksel controller
Self Tests artık standart ısıtıcı başına H01/H05/H06/H07/H08/H09/H13 sunar.
Seçim salt-okunur ön kontroldür; ayrı onay mevcut tamamlanma takipli WebSocket
RPC üzerinden tam 120 sn ısıt/bekle/OFF programını gönderir.
Durum/kuyruk okumaları yalnız test sırasında yaklaşık saniyede bir ortak sınırlı
worker ile yapılır. İki sıfır hedef/sıfır görev oranı örneği ve 32 sn soğumadan
sonra süresiz kullanıcı gözlemi sorulur. Ölçüt başarısı tek başına PASS değildir.

**Aktif termal testi durdurmak Klipper acil shutdown ister.**
Bu G-code beklemesini aşar; normal OFF bu beklemenin arkasında kalabilirdi.
Onay ekranı bu davranışı bildirir. Güvenlik/telemetri belirsizliği, beklenmeyen
hedef, diğer ısıtıcı, baskı/işlem çakışması veya teknik süre aşımı da bir kez
shutdown ister, sonraki ısıtmayı kilitler ve yanıt yoksa shutdown'ın
doğrulanamadığını açıkça bildirir. Otomatik yeniden başlatma yapılmaz.
Shutdown yanıtı bağımsız elektriksel OFF kanıtı değildir. Petrel kapanırsa da
süreli program OFF ile biter; Klipper korumaları korunur.
Petrel donanımsal güvenlik controller'ı değildir.
Soğuk/boş başlangıç, yapılandırılmış sınırlar, yaşam döngüsü/epoch kimliği ve
taze dispatch kontrolü zorunludur. Sıfırdan farklı eski ısıtıcı hedefi geri
yüklenmez. Bütün H hedeflerinin fiziksel kabulü son toplu kullanıcı testine
kadar bekler. Genel/uygulamaya özel ve ileri kalibrasyon adaptörleri bu
aşamada henüz kullanılamaz.
