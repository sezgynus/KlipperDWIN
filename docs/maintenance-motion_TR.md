# Hareket Maintenance

## Test içinde gerekli homing hazırlığı

17 Ekim `0f7da07e7fe6402985255baaeb09e8bf` kaydında M04/X, yalnız eksenler home edilmediği için hareket göndermeden BLOCKED oldu. Artık M04/M05/M06 ve M12'nin başlangıç ön kontrolünde eksik XYZ/faz geçmişi varsa aynı test sahibi içinde homing hazırlığı açılır. UI `Home XYZ, then run test` diyerek hem homing hem seçilen test için boş-yol onayı alır. Mevcut güvenlikli G28+M400 protokolü ve iki taze XYZ/mod geri okuması tamamlanınca seçilen test yeni ön kontrol ve gönderim guard'ından geçerek ikinci başlangıç onayı istemeden devam eder. Zaten home edilmiş testte gereksiz homing yapılmaz. Aynı test içinde hazırlık yalnız bir kez denenir; hareket hatası tekrar oynatılmaz.

Homing hata/iptalinde asıl test başlamaz; aktif iptal güvenlik durdurmasını kullanır. Homing sonrasında da soğuk/OFF ısıtıcı, desteklenen kinematik/komutlar, konum sınırları, motor etkinliği, Z açıklığı, mesh ve yaşam döngüsü kontrolleri korunur. Gerekli güvenli test konumu veya mesh temizliği otomatik varsayılmaz. M06'nın ölçüm ve dönüş aşamasında yeniden homing yapılmaz; dönüş kendi onayını korur. Tanılama okumaları homing başlatmaz. Logger seçilen test kimliğini, hazırlık alt aşamasını, homing RPC/okumalarını ve teste devamı ayrı kaydeder. Bu kod/CI değişikliği yeni fiziksel kabul vermez.

M07/M08/M09 (sürücü durum/sıcaklık/akım), M11 (enable durumu),
M12 (son homing fazı), M13 (yalnız angle sürücüsü sıcaklık telemetrisi),
M14 (komutlanan toolhead durumu) ve M16 (bilinen carriage modları)
kullanıcı isteğiyle Diagnostics altında okunur. Mevcut kuyruk/yaşam döngüsü/
oturum kontrolleri ve sınırlı read worker kullanılır. Motor açılmaz,
homing/hareket yapılmaz. Register/config yazılmaz.
Null sürücü monitor durumu sonuçsuzdur; sıcaklık üretilmez.
Klipper drv_status içinde yalnız sıfır olmayan alanları bildirir; boş mapping
ile null farklıdır. Konum komutlanan durumdur, fiziksel mesafe ölçümü değildir.
M12 tanılaması kalibrasyon veya kayıt yapmaz. Angle durumu mil açısı değildir.
Fiziksel kabul değişmez. M02/M17 bilerek gizli kalır.

## M01 ve M10
M01 fiziksel ana eksen endstop'u başınadır: serbest, basılı tutulmuş, serbest
durumlar Moonraker'ın gerçek endstop endpoint'inden açık kullanıcı eylemiyle
okunur. Hareket ve last_query tekrar kullanımı yoktur. Sorular süresizdir;
uyuşmayan durum açıkça yeniden okunabilir. Sanal/sensorless endstop'lar hariçtir.
Son gözlem geçişlerden ayrıdır; serbest okuma geri yükleme kanıtıdır.
M10 motor açmadan ve DUMP_TMC kullanmadan TMC2208'in yapısal monitor durumunu
okur. Null monitor bilinmeyendir; standstill/açık yük işareti kısa devre/aşırı
sıcaklık diye uydurulmaz. Geçerli boş, sıfır olmayan alanlar mapping'i raporlanan
kritik/uyarı bayrağı yok demektir; motor sağlığı kanıtı değildir. Son operatör
onayı OBSERVED_USER'dır, otomatik donanım PASS'i yoktur. Diğer çipler kendi
hata şeması gerektirir. Mevcut F/H kabul kayıtları değişmez.

## Hareket sözleşmeleri
Cartesian/CoreXY koordinat hareketi gerçek XYZ homing, yapılandırılmış sınırlar,
soğuk/OFF ısıtıcılar, açık ana motorlar ve açık boş-yol onayıyla sınırlıdır.
M04 yalnız ana Cartesian motorlarda Klipper'ın 10 çevrimlik 1 mm STEPPER_BUZZ
komutunu kullanır; bağımsız çoklu Z ve bağlı motor buzzing kabul edilmez.
M05 en çok 5 mm/sn XY / 1 mm/sn Z ile 1 mm gidip dönme derler. M06 tek
10 mm ileri hareket derler; ayrı onaylı dönüş aynı ölçüm durağı konumunu ister.
Eksik homing, açık hazırlık onayından sonra testin içinde tamamlanır. XYZ sınırlarında 2 mm pay; XY için
en az 5 mm Z açıklığı gerekir. Yüklü mesh/bilinmeyen dönüşüm, carriage ve
override edilmiş protokol komutları kapatılmak yerine testi engeller.
Benzersiz SAVE/RESTORE_GCODE_STATE MOVE=0 modal ayarları korur; M400 hareket
bitimini bekler. FORCE_MOVE, SET_KINEMATIC_POSITION ve ayar yazımı yoktur.
M03 açıkça seçilen yapılandırılmış XYZ homing'dir; homing_override/macro G28
reddedilir. M12 yalnız yapılandırılmış fiziksel endstop phase, gerçek last_home
geçmişi ve bekleyen config yokken derlenir; kaydetmeden trigger_phase bekletir.
Yazılım geri okuması fiziksel konum kanıtı değildir. Salt derleyici aşağıda açıklanan kayıtlı controller/UI akışına bağlıdır.

## Kayıtlı fiziksel controller
M03/M04/M05/M06 ve stepper bazlı M12 artık fiziksel router'a katılır. Satır
seçimi salt-okunur ön kontroldür; ayrı boş-yol onayı tek guarded tamamlanma
RPC'sini gönderir. Aktif adımlarda sınırlı durum/kuyruk verisi yenilenir.
İki taze geri okuma beklenen komutlanan konum/modal ayarları doğrular;
kullanıcı gözlemi yine zorunludur. Gerçek mesafe ölçülmüş sayılmaz.
Aktif iptal, güvensiz yaşam döngüsü/kuyruk/işlem, belirsiz komut veya eksik
geri yükleme kanıtı bir kez acil shutdown ister; tekrar/kör ters hareket yoktur.
Belirsizlik sonrasında controller yeni hareketi kilitler. Sonlu normal
protokoller modları kendi programında geri yükler; firmware korumaları korunur.

M06 10 mm ileri hareketten sonra durur. Gerçek cetvel/kumpas mesafesini encoder
ile gir (0,01 mm adımlar); başlangıçtaki 10 mm yalnız değiştirilebilir öneridir,
açık operatör girişi/onayı olmadan kabul edilmez. Ters hareketten önce yeni
ön kontrol ve ayrı Return to start onayı gerekir. Sabit ölçüm ve dönüş onayı
ekranları süresizdir. Değişmiş konum/mod, kapalı motor veya kayıp homing,
tahmin edilmek yerine dönüşü engeller. Sabit aşamada iptal arabayı ölçüm
durağında bırakır; otomatik dönüş yapmaz, geri yükleme false bildirilir.
En çok 0,2 mm hata + doğrulanmış dönüş/kullanıcı gözlemi bu sınırlı tanılamayı
geçirir; rotation_distance değişmez. Bu kullanıcı bildirimi ölçümüdür;
kalibre metroloji iddiası değildir.

M12 bir yapılandırılmış fiziksel endstop stepper'ı için mevcut Klipper homing
geçmişini kullanır. Eksen/geçmiş eksikse önce onaylı homing yapılır; SAVE_CONFIG yoktur. Tam hedefin bekleyen
trigger_phase sonucu, korunmuş mod/konum ve sonra kullanıcı gözlemi gerekir.
Bekleyen kalibrasyon config'i bilerek geri alınmadığı için sonuç OBSERVED_USER,
restore_verified=false olur. Önceden bekleyen config başlangıcı engeller.
M01 ve M12 katalog kapsamları cihaz satırlarını destekler; cihaz bazlı kanıt
yokken eski global bilgi fallback'i korunur. Uygulama ve CI fiziksel kabul vermez.

## Son kapsam ve saha sırası
| ID | Sunulan |
|---|---|
| M01 | Ana fiziksel eksen switch'inde serbest/basılı/serbest; hedef bazlı |
| M02 | Sanal endstop'a elle basma pseudo-test'i bilerek gizli |
| M03 | Boş-yol onaylı, desteklenen yapılandırılmış XYZ homing |
| M04 | Ana Cartesian motor buzz; bağımsız çoklu Z/bağlı motor buzzing yok |
| M05 | Desteklenen koordinat XYZ 1 mm gidip dönüş |
| M06 | Harici gerçek 10 mm mesafe girişi ve ayrı onaylı dönüş |
| M07 | Yalnız sürücü monitor BİLGİSİ; null bilinmeyen |
| M08 | Keşfedilmişse yalnız gerçekten raporlanan sürücü sıcaklığı |
| M09 | Raporlanan akım ayarı; ölçülmüş sargı akımı değil |
| M10 | Tam TMC2208 şemalı pasif hata/uyarı kontrolü ve kullanıcı gözlemi |
| M11 | Motor enable bilgisi |
| M12 | Yapılandırılmış fiziksel stepper başına bekleyen faz kalibrasyonu; last_home tanılaması |
| M13 | Mevcut angle sürücüsü sıcaklık durumu; mil açısı uydurulmaz |
| M14 | Komutlanan konum/homing/azami hız bilgisi |
| M15 | Uygulamaya özel sözleşme olmadan genel manual_stepper hareket adaptörü yok |
| M16 | Desteklenen raporlanmış carriage mod alanları; carriage aktivasyonu yok |
| M17 | Ham force/register yazma pseudo-test'i bilerek gizli |

Referans M çizelgesindeki 22 doğrulanmış hedefin adaptörü mevcut; dört M07
satırı bilgi adaptörüdür, işlevsel motor testi değildir. Hepsi fiziksel kabul
bekliyor; F/H kabul durumları değiştirilmedi. Diğer sürücü hata şemaları ve
genel manual_stepper'lar keşfedildi diye fiziksel test olarak sunulmaz.

Saha sırası: Yazıcı sabitken ve switch'ler erişilebilirken M01 X/Y;
yatağı/homing yolunu boşalttıktan sonra M03; ardından normal yazıcı kontrolleriyle
homing yapılmış arabayı iç, yükseltilmiş, yolu boş bir konuma bilinçli getir.
Isıtıcıları soğutarak desteklenen X/Y/Z için M04/M05/M06'yı sırayla uygula.
Ana motorları açık tut; sözleşme mesh temizliği istiyorsa bunu kendin yönet.
Test kompanzasyonu temizlemez; eksik homing'i açık onayla hazırlık aşamasında tamamlar.
Boş alan onayı, yataktaki rastgele nesnelerin geometrisini otomatik kanıtlamaz.
Test yazıcının sahibiyken kuyruktan baskı/harici hareket başlatma. Yerel Petrel
hareket guard'ları rakip sahipli işlemleri reddeder; bu yazılım rezervasyonu
harici istemcileri kilitlemez.

M10 ve M07'yi gerçekten sürücü monitor verisi varken uygula; kapalı/null
sonuçsuzdur, sağlık onayı veya otomatik motor açma nedeni değildir.
M12 en son: bilinçli normal homing ile faz geçmişi elde et, tam yapılandırılmış
phase stepper'ı seç, bekleyen kalibrasyonu inceleyip onayla, sonucu kaydet.
İkinci ekseni kalibre etmeden bekleyen config'i açıkça yönet. SAVE_CONFIG
otomatik değildir. M12 sonucu bekleyen config geri alınmadan OBSERVED_USER
kalır; elektriksel/metrolojik doğrulama iddiası yoktur.

Geliştirme sırasında lokal test/emülatör veya gerçek fiziksel hareket yapılmadı.
Kontroller bot imzalı feature HEAD'de GitHub Actions ile çalışır. M için de
sonucun geldiği menü/seçime dönüş ve süresiz operatör soruları korunur.

Son denetim: M12 faz geçmişi isteğe bağlı okunur; global aboneliğe eklenmez.
Dispatch mevcut abonelikten konum/mod/homing/bekleyen config'i yeniden denetler.
Mesh ön kontrolünde yalnız profil ve sınırlar istenir; matris çekilmez.
Bilinmeyen TMC2208 register şeması sonuçsuz kalır. Bilgi kaynağı reddi
rezervasyonu bırakır. Onay ekranındaki bilgi satırları işlem yapmaz; ölçülen
mesafe editörü anlık yenilenir ve dönüşü kendiliğinden başlatmaz.

## 17 Ekim fiziksel doğrulama — homing öncesi konum

M01 fiziksel X/Y endstop'ları açık kullanıcı gözlemiyle geçti.
İkinci kayıt oturumunda (`2de3566ce59d476cb020ad83dd5360bf`, 787 olay, kayıp yok)
M03 ve sonraki 11 deneme komut gönderilmeden aynı geometri denetiminde engellendi:
`homed_axes=""`, konum `[0,0,0]`, minimumlar `[1.5,7,-5]`.
Bu, 12 ayrı motor arızası değildir.

M03 homing öncesi bilinmeyen eksenlerin geçici sıfırını fiziksel konum kabul etmez;
yapılandırılmış sonlu/artan sınırlar, soğuk/OFF ısıtıcılar, modlar, override,
yaşam döngüsü ve ayrı kullanıcı onayı hâlâ denetlenir.
Zaten home edilmiş eksenlerin konumu sınır içinde olmalıdır.
Homing sonrası tüm XYZ, konum ve modal geri okumaları doğrulanır.
Bu eski kayıtta M04/M05/M06 home yapılmamışsa `home_xyz_before_motion_test` veriyordu; güncel hazırlık akışı bunu onaylı homing'e çevirir.
M12'nin kendi eksen/last_home denetimleri korunur.

Yeniden testte önce yalnız M03'ü çalıştırın. Tamamlandıktan sonra normal Move menüsüyle
XYZ'yi sınırlardan en az 2 mm içeri, XY hareketi için Z'yi alt sınırdan en az 5 mm
yukarı ve mekanik açıdan açık bir konuma getirin; motorlar açık kalsın.
M04/M05/M06 ardından çalıştırılır. Aktif mesh varsa testin istediği mevcut normal
mesh temizleme akışını kullanın. M12'yi homing geçmişi oluştuktan sonra en sona bırakın;
bekleyen config varken yeni kalibrasyon başlatılmaz.

## 17 Ekim M03 aktif kuyruk kanıtı düzeltmesi

Oturum `69bd4367df274301b8e2f3275b493378`, HEAD `b60d729`: 448 olay,
kayıp/yazma hatası yok. M03 ön kontrolü geçti; G28+M400 gönderildi, yaklaşık
0,23 saniye sonra aktif güvenlik kontrolü shutdown istedi. Fiziksel kabul verilmedi.

Son kuyruk okuması monotonik 580503,541; gönderim 580506,430;
ilk aktif kontrol 580506,657 idi. Kanıt gönderimde yaklaşık 2,89 saniyelik,
ilk kontrolde 3,12 saniyelikti. Kontrolcü ilk taze okumayı toplamadan
eski kabul kanıtının 3 saniyelik süresini aktif teste uyguluyordu.

Yeni davranış: ilk aktif okuma hemen planlanır; bitmiş worker sonucundaki
taze kuyruk kanıtı eski kanıtın yaşından önce değerlendirilir.
Başlatma/gönderim sınırı 3 saniye kalır. Aktif komutta mevcut 5 saniyelik
okuma watchdog'u kuyruk tazeliği için de kullanılır; termal kontrolcüyle aynıdır.
Print/SD/pause/MMU/diğer-owner ve epoch kontrolleri her tick'te canlı kalır.
5 saniyeyi aşan/bilinmeyen kanıt veya gerçek çakışma yine acil shutdown verir.
Kayıt, kesin `safety_reason` ve `queue_age_s` değerlerini de tutar;
kuyruk yaşı yalnız saniyelik örneğe girer, her tick için yeni aşama üretmez.

M03'ün ikinci başlatma isteği mevcut belirsizlik kilidinde reddedildi;
komut tekrar gönderilmedi. Güvenli/OFF durum doğrulandıktan ve güncel
Petrel servisi başlatıldıktan sonra yalnız M03 yeniden denenmelidir.

## Onay ekranına tekrar dönme düzeltmesi

17 Ekim son M03 kaydında ilk iki onay, 3 saniyelik kanıt eskidiği için ön kontrole ve Cancel seçimine döndü; üçüncü onay hareketi başlattı. Bu bir UI akış kusurudur. Artık aynı hareket için verilen onay, en fazla 12 saniyelik salt-okunur güvenlik yenilemesi sırasında korunur. Ekran Refreshing safety / Your confirmation is kept gösterir. Taze kuyruk, yaşam döngüsü, konum, modlar ve aynı program tekrar doğrulanmadan komut gönderilmez; koşullar değişirse BLOCKED olur. İptal hareket göndermez. M06'nın ilk hareket ve dönüş onayları hâlâ ayrıdır. Komut hatası tekrar denenmez.

Geçici kayıt confirm_attempts, refresh_reason ve confirmation_safety_refresh akış olayını içerir; test sürerken test sayfasından çıkış left_test_while_pending olarak ayrıca işaretlenir. M03 fiziksel kabulü korunur; bu UI düzeltmesinin fiziksel doğrulaması bekliyor.
