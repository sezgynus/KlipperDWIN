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
Standart başlangıç hedefleri hotend 60 C / yatak 45 C, süre 120 sn'dir.
Testteki sıcaklık ölçümleri için Klipper'ın yapılandırılmış min_temp/max_temp
sınırları esas alınır. H07 aşımı ayrı bir performans ölçütü olarak raporlar.
Yapılandırılmış bütün ısıtıcılar sıfır hedef ve sıfır görev oranıyla başlamalıdır.
Genel ısıtıcılar açık uygulama profili gerektirir; hazne sıcaklığı tahmin edilmez.
Salt derleyici, süreli bekleme sonrasına OFF ekler. SAVE_CONFIG yoktur.

## Fiziksel controller
Self Tests artık her standart ısıtıcı için tek bir **Thermal Characterization**
(H01) satırı sunar. Tek ısıtma/bekleme/OFF/soğuma döngüsünden H01/H05/H06/
H07/H08/H09/H13 ölçümleri ve ayrı ayrı kullanıcı onaylı sonuçlar çıkar.
Yedi kimlik katalogda, trace ve geçmiş kayıtlarında bağımsız kalır; yalnız
fiziksel test oturumları birleştirilir. H02/H03/H04 PID ayrı kalır.
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
Petrel, Klipper'ın `save_config_pending_items` nesnesinde büyük/küçük
harfe duyarlı `pid_Kp`, `pid_Ki`, `pid_Kd` alanlarını ilgili ısıtıcının
tam bölüm adında (`extruder`, `heater_bed` veya `heater_generic NAME`)
okur. LCD/geçmiş kanıt adları uyumluluk için `pid_kp`, `pid_ki`,
`pid_kd` kalır. Bu üç sayısal değer yoksa başarılı Klipper komutu bile
PID arızası değil, INCONCLUSIVE doğrulama sonucudur. PID katsayıları
Klipper'da bekler; Petrel SAVE_CONFIG çağırmaz. Önceki testten kaydedilmemiş
ayarlar varken sonraki PID testi `existing_or_unknown_pending_config`
nedeniyle BLOCKED kalır. Kullanıcı önce bu değişiklikleri bilinçli olarak
kaydetmeli veya iptal edip uygun biçimde yeniden başlatmalıdır;
Petrel bekleyen ayarların üzerine sessizce yazmaz.
Sabit beklemeli testlerden farklı olarak PID süresini Klipper autotune belirler.
Petrel kapanırsa host izlemesi kaybolur; kalibrasyonu gözetimsiz bırakmayın.
İptal veya teknik hata acil shutdown ister; otomatik tekrar yoktur.
H04 genel ısıtıcılar hâlâ uygulamaya özel güvenli profil gerektirir.

## Açık genel ısıtıcı uygulamaları (H04)
İsteğe bağlı ~/.config/Petrel/maintenance-thermal-profiles.json yalnız READY
aşamasında okunur. Sürüm 1 {"version":1,"heaters":[{"object":"heater_generic dryer",
"target":45,"duration_s":120}]} biçimini destekler. Eski sayısal
`ceiling` alanı geriye dönük uyumluluk amacıyla kabul edilir; kullanılmaz.
Bu uygulama beyanıdır; örneğin kurutucunuz için güvenli olduğunun kanıtı değildir.
Sınırları gerçek cihazdan seçin. En çok 8 tam keşfedilmiş genel ısıtıcı ve
4096 bayt; bilinmeyen alan/tekrar/sonlu olmayan değer tüm profili reddettirir.
Yapılandırılmış min_temp < hedef < max_temp ve 30..120 sn süre gerekir. Donmuş profil token'ları aynı snapshot'a katılır; menü girişinde veya
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

## **Termal güvenlik yenilemesinde tek onay (17 Ekim 2026)**

H01/H02/H03/H04/H05/H06/H07/H08/H09/H13 seçildiğinde ilk aşamada
yalnız soğuk/boş güvenlik ön kontrolü yapılır; ayrıca
`Run thermal test` (veya `Run PID`) onayı gösterilir. Kullanıcının
bu eylemi seçmesi, ekrandaki bilgileri incelerken ilk kuyruk kanıtı
eskimiş olsa da **yalnız bu işlem için bir kez verilmiş açık onaydır**.
Petrel bu durumda `Refreshing HEAT safety` ekranını gösterir, yeni
soğuk/boş/kuyruk/diğer ısıtıcı kanıtı toplar ve yalnız taze, olumlu
doğrulamanın ardından ikinci kez tıklatmadan tek korumalı ısıtma
programını gönderir. Eski kanıt komut yetkisi sağlamaz. Socket gönderimi
öncesinde canlı güvenlik, termal sözleşme ve epoch kontrolleri tekrar
zorunludur. Yenilenen ön kontrol başarısızsa, eskirse veya kesilirse
G-code gönderilmez, otomatik yeniden deneme yapılmaz, BLOCKED bildirilir;
ısıtma başlamadan iptal acil shutdown istemez. Gönderilmiş ya da
gönderimi belirsiz aktif ısıtma için mevcut shutdown güvenliği korunur.
Kullanıcı ilk onaydan önce süresiz bekleyebilir; hareketsizlik nedeniyle
test sonlandırılmaz veya tekrar onay istenmez. Isıtma öncesindeki
başlatılmamış süre sayacı artık hatalı büyük süre göstermez.
Bu düzeltme H grubunun tamamında ortaktır; CI fiziksel kabul değildir.

**17 Ekim 2026 termal ölçüm düzenlemesi:** Önceden Petrel'in
`target + 10 C` hesabına dayanan denetimi yerine yazıcıda yapılandırılmış
Klipper sıcaklık sınırları kullanılır. Bu düzenleme H02/H03 PID salınımlarının
hedef üstündeki geçerli ölçümlerini kapsar. H07'nin 5 C aşım ölçütü sonuç
değerlendirmesidir; sıcaklık denetim eşiği değildir. Diğer çalışma güvenliği,
OFF doğrulaması ve operatör onayı değişmedi. CI fiziksel kabul sayılmaz.

## Birleşik termal karakterizasyon (17 Ekim 2026)
Keşfedilmiş her ısıtıcı için tek H01 seçimi, sınırlandırılmış bir sıcaklık
serisini ölçer ve yedi bağımsız ölçütü değerlendirir. Kullanıcı ısıtmadan
önce bir kez onay verir; OFF ve soğuma doğrulandıktan sonra tek fiziksel
gözlem yanıtı verir. Her özellik kendi durumuna ve sayısal kanıtına sahiptir.
Ölçüm penceresi eksikse INCONCLUSIVE, ölçülen kriter sağlanmadıysa
FAILED_METRIC, kullanıcı gözlemi olumsuzsa FAILED_USER yazılır.
Toplu sonuç özet durum taşır; geçmişe ortak zaman damgasıyla yedi ayrı
özellik kaydı tek worker yazımıyla aktarılır. Trace, yedi alt sonucun
kimlik ve kanıtlarını tek sonuç olayı altında saklar. CI fiziksel kabul
JSON'unu değiştirmez. LCD'de yedi durum/ölçüm çifti kaydırılarak incelenir,
Back önceki Self Tests satırına döner. Mevcut 120 sn bekleme otomatik uzatılmaz.
