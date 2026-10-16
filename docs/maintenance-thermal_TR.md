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

## PID kalibrasyonu
H02 hotend ve H03 yatak ayrı kalibrasyon kayıtlarıyla Klipper PID_CALIBRATE
kullanır; hedefler sırasıyla 150 C / 60 C'dir. Başlangıçta ısıtıcıların soğuk/boş
olması ve bekleyen config değişikliği bulunmaması gerekir. Tamamlanma RPC'si
en çok 900 sn tutulur; autotune sırasında telemetri, kuyruk ve yaşam döngüsü
izlenir. Klipper'ın normal hedef salınımı (hedef veya hedef eksi 5 C) kabul
edilir; ilgisiz hedef değişimi reddedilir. Program sona OFF ekler.
Başarılı RPC, tam ilgili ısıtıcı için yeni bekleyen pozitif/sonlu Kp/Ki/Kd,
iki sıfır hedef/sıfır görev oranı örneği ve açık kullanıcı gözlemi birlikte gerekir.
PID katsayıları Klipper'da bekler; Petrel SAVE_CONFIG çağırmaz.
Sabit beklemeli testlerden farklı olarak PID süresini Klipper autotune belirler.
Petrel kapanırsa host izlemesi kaybolur; kalibrasyonu gözetimsiz bırakmayın.
İptal veya teknik hata acil shutdown ister; otomatik tekrar yoktur.
H04 genel ısıtıcılar hâlâ uygulamaya özel güvenli profil gerektirir.

## Açık genel ısıtıcı uygulamaları (H04)
İsteğe bağlı ~/.config/Petrel/maintenance-thermal-profiles.json yalnız READY
aşamasında okunur. Sürüm 1 tam olarak {"version":1,"heaters":[{"object":"heater_generic dryer",
"target":45,"ceiling":55,"duration_s":120}]} biçimindedir.
Bu uygulama beyanıdır; örneğin kurutucunuz için güvenli olduğunun kanıtı değildir.
Sınırları gerçek cihazdan seçin. En çok 8 tam keşfedilmiş genel ısıtıcı ve
4096 bayt; bilinmeyen alan/tekrar/sonlu olmayan değer tüm profili reddettirir.
Hedef < tavan < yapılandırılmış max_temp, 5..15 C marj ve 30..120 sn süre
gerekir. Donmuş profil token'ları aynı snapshot'a katılır; menü girişinde veya
encoder tick'inde dosya okuma yoktur. Canlı soğuk/OFF, diğer ısıtıcı, güvenlik
ve dispatch kontrolleri yine zorunludur. H04 tanımlanan hedefi ve ayrı 900 sn
kalibrasyon sınırını kullanır. Profil yoksa genel testler gösterilmez.
Standart extruder/yatak testleri profil dosyası gerektirmez.

## H01–H18 kapsamı
| ID | Uygulama / gereken kanıt |
|---|---|
| H01 | Kontrollü ısıtma; her ısıtıcı ayrı hedef |
| H02 / H03 | İzlenen hotend / yatak PID; otomatik kayıt yok |
| H04 | Açık profilli genel uygulamalar için aynı izlenen PID |
| H05 / H06 | Isıtma eğimi / hedefe erişme; ayrı ölçüt |
| H07 / H08 | Aşım / yerleşmiş kararlılık; ayrı pencere |
| H09 | Sıfır hedefte en az 30 sn soğuma eğimi |
| H10 | Koşullu: uyumlu ölçülmüş baseline yok; çalıştırılabilir adaptör yok |
| H11 | Cihaz bazlı raporlanan görev oranı Diagnostics |
| H12 | Koşullu: doğrulanmış nominal watt + görev oranı geçmişi yok; enerji tahmini yok |
| H13 | Normal güvenli ısıtma tepkisi; kasıtlı runaway yok |
| H14 | Isıtıcılar dahil zaman damgalı sıcaklık Diagnostics |
| H15 | Koşullu: doğrulanmış eş konumlu kalibre sensör çifti yok; çalıştırılabilir adaptör yok |
| H16 | Yalnız gerçek çevre alanları keşfedilmişse Diagnostics |
| H17 | Koşullu: probe drift kalibrasyonu hareket/ısıtma da yapar; özel hareket/termal sözleşme yok, gösterilmez |
| H18 | Koşullu: tekrarlanabilir izinli fan/ısıtıcı A/B profili yok; gösterilmez |

**Kapsam sınırı:** referans yazıcıda doğrulanmış 16 fiziksel H hedefinin tamamı
uygulandı ve fiziksel kabul bekliyor. H10/H12/H15/H17/H18 uygulanmış donanım
adaptörleri değildir; keşif veya katalog satırı bu durumu değiştirmez.
Bu isteğe bağlı testler açılmadan önce ek kanıt ve bağımsız sözleşme gerekir.
18 ID'nin hepsinin çalıştırılabilir olduğu iddia edilmez.

## Son toplu fiziksel kabul
Geliştirme sırasında fiziksel komut gönderilmedi. Gerçek boş yazıcıda önce
checkout/servis HEAD'ini ve etkin ısıtıcı sınırlarını doğrulayın.
1. Diagnostics altında H11/H14 ve gerçekten mevcutsa H16'yı inceleyin.
2. H01'i hotend ve yatak için bağımsız çalıştırın. Onaydan önce hedefi ve
   shutdown bildirimini okuyun. Gözlenen ısıtma ve OFF davranışını doğrulayın.
3. Isıtıcılar soğuk başlangıç koşuluna döndüğünde H05, H06, H07, H08, H09
   ve H13'ü her hedef için ayrı çalıştırın. Her satır ayrı deney ve sonuçtur;
   komşu satırlara kabul aktarılmaz.
4. H02 ve H03'ü en son, gözetim altında, tek ısıtıcıyla yapın. Bekleyen
   config kalibrasyonu engeller; önceden bekleyen PID sonucunun ne olacağına
   kendiniz karar verin. Petrel otomatik kaydetmez/Klipper'ı yeniden başlatmaz.
5. Tam özellik/hedefi, LCD sonucunu, gözlemi ve geri yükleme kanıtını kaydedin.
   Ancak bundan sonra ilgili hedefin kanonik JSON ve iki çizelgesini güncelleyin.
Aktif durdurma Klipper shutdown demektir; yazıcı kontrol edildikten sonra
operatörün firmware'i yeniden başlatması gerekebilir. Shutdown yanıtı yoksa
fiziksel ısıtıcı gücü hemen kontrol edilmelidir. Otomatik tekrar yoktur.
CI fiziksel kabul değildir. Lokal test veya emülatör çalıştırılmadı.

PID ayrıca pozitif raporlanan görev oranı ve hedef eksi 5 C bandına ölçülmüş erişme gerektirir. Soğuma sırasında yeniden aktif ısıtıcı shutdown ister. Sonuçta seçilen testin ana metriği LCD'de ilk gösterilir.

Isıtma programı `G4` sonrasında `M400` ile gerçek beklemenin tamamlanmasını bekler; ardından OFF gönderir. G4/M400 veya termal komutların macro ile override edildiği yapılandırmalar güvenilir protokol kabul edilmez.

## 16 Ekim 2026 kullanıcı deneyi ve düzeltme
Kullanıcı H01/H05/H07/H08/H09/H13 ve H06 hotend denemelerinde
webhooks shutdown veya Run ekranına geri dönüş bildirdi. H02/H03
`pid_calibrate interrupted` bildirdi; H03 yaklaşık 10 sn ısıttı.
H05/H07 yatak BLOCKED idi. H06 yatak çalıştı; paylaşılan sonuç
PASSED_USER, hedefe erişme 33.57 sn, 122 örnek, 153.8 sn toplam pencere
gösteriyor. H11 hotend/yatak ve H14 görünen okumalar kullanıcı tarafından
çalışır olarak bildirildi. Bu bilgi okumalarından fiziksel ısıtıcı kabulü türetilmez.
Diğer hedefler için başarılı fiziksel kabul yoktur.

Controller'da tamamlanmış yeni kuyruk okumasından önce eski kanıtın yaşının
denetlenmesi düzeltildi. Dispatch öncesi 3 sn kuralı korunur; devam eden
testte kuyruk kanıtının sınırı telemetri watchdog'u ile aynı 5 sn'dir.
Canlı baskı/işlem ve epoch kontrolleri her tick devam eder. Dispatch guard'ı
komutu gönderilmeden reddederse soğuk test BLOCKED döner; acil shutdown
göndermez. Gönderilmiş veya gönderimi belirsiz komut hataları hâlâ shutdown
ister. Örnek/işlem hatasının alt nedeni sonuç kodunda korunur.

Klipper'ın PID hedef davranışı kaynakta yeniden kontrol edildi: hedef ve
hedef eksi 5 C geçişleri zaten destekleniyordu; bu kural değiştirilmedi.
Bu düzeltme gerçek cihazda henüz yeniden denenmedi. PID kesilmesinin kesin
nedeni için yeni sonuç kodu ve aynı zamana ait Klipper/Petrel günlüğü gerekir.
Sıcak veya başka ısıtıcısı etkin yazıcıda BLOCKED normaldir; yatakta başlangıç
sıcaklığı en çok 35 C, hotend'de en çok 45 C olmalıdır.
