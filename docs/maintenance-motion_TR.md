# Hareket Maintenance

## Test içinde gerekli homing hazırlığı

17 Ekim `0f7da07e7fe6402985255baaeb09e8bf` kaydında M04/X, yalnız eksenler home edilmediği için hareket göndermeden BLOCKED oldu. Artık M04/M05/M06 ve M12'nin başlangıç ön kontrolünde eksik XYZ/faz geçmişi varsa aynı test sahibi içinde homing hazırlığı açılır. UI `Home XYZ, then run test` diyerek hem homing hem seçilen test için boş-yol onayı alır. Mevcut güvenlikli G28+M400 protokolü ve iki taze XYZ/mod geri okuması tamamlanınca seçilen test yeni ön kontrol ve gönderim guard'ından geçerek ikinci başlangıç onayı istemeden devam eder. Zaten home edilmiş testte gereksiz homing yapılmaz. Aynı test içinde hazırlık yalnız bir kez denenir; hareket hatası tekrar oynatılmaz.

Homing hata/iptalinde asıl test başlamaz; aktif iptal güvenlik durdurmasını kullanır. Homing sonrasında da soğuk/OFF ısıtıcı, desteklenen kinematik/komutlar, konum sınırları, motor etkinliği, Z açıklığı, mesh ve yaşam döngüsü kontrolleri korunur. Gerekli güvenli test konumu veya mesh temizliği otomatik varsayılmaz. M06'nın ölçüm ve dönüş aşamasında yeniden homing yapılmaz; dönüş kendi onayını korur. Tanılama okumaları homing başlatmaz. Logger seçilen test kimliğini, hazırlık alt aşamasını, homing RPC/okumalarını ve teste devamı ayrı kaydeder. Bu kod/CI değişikliği yeni fiziksel kabul vermez.

M07/M08/M09 (sürücü durum/sıcaklık/akım), M11 (enable durumu),
M12 (son homing fazı), M13 (yalnız angle sürücüsü sıcaklık telemetrisi),
M14 (komutlanan toolhead durumu) ve M16 (bilinen carriage modları)
kullanıcı isteğiyle Diagnostics altında okunur. Mevcut kuyruk/yaşam döngüsü/
oturum kontrolleri korunur. M07, desteklenen TMC'lerin register'larını
istek üzerine Klipper DUMP_TMC ve mevcut Moonraker WebSocket'iyle doğrudan okur;
homing öncesinde ve sürücü enable kapalıyken de çalışır. Motor etkinleştirme,
homing/hareket veya register/config yazma komutu gönderilmez. Diğer
tanılamalar sınırlandırılmış GET kullanır. Kayıp/hatalı register cevabı
hatasız sürücü kanıtı değil, bilinmeyen/iletişim hatası sonucudur;
sıcaklık uydurulmaz. Konum komutlanan durumdur, fiziksel mesafe ölçümü değildir.
Pasif M12 tanılaması kalibrasyon veya kayıt yapmaz; ayrı stepper bazlı M12 testi otomatik kaydetmeden kalibrasyon yapar. Angle durumu mil açısı değildir.
Fiziksel kabul değişmez. M02/M17 bilerek gizli kalır.

## M01 fiziksel endstop ve M07 pasif sürücü tanılaması
M01 fiziksel ana eksen endstop'u başınadır: serbest, basılı tutulmuş, serbest
durumlar Moonraker'ın gerçek endstop endpoint'inden açık kullanıcı eylemiyle
okunur. Hareket ve last_query tekrar kullanımı yoktur. Sorular süresizdir;
uyuşmayan durum açıkça yeniden okunabilir. Sanal/sensorless endstop'lar hariçtir.
Son gözlem geçişlerden ayrıdır; serbest okuma geri yükleme kanıtıdır.
M07 desteklenen TMC'lerde artık önbellekteki drv_status alanına bağımlı değildir.
Kullanıcı seçtiğinde `DUMP_TMC STEPPER=<doğrulanmış-stepper> REGISTER=DRV_STATUS`
komutunu bir kez gönderir; G28, motor enable ve yapılandırma/register yazımı yoktur.
Klipper'ın gerçek register yanıtı G-code RPC sonucunda değil,
`notify_gcode_response` bildiriminde gelir. Petrel mevcut sınırlı yanıt
imlecini ve komut tamamlanmasını kullanır, eski/kayıp/belirsiz yanıtı reddeder.
TMC2208 için ham bitlerden fault_count, faults, standstill, akım ölçeği,
stealth ve varsa açık-yük göstergeleri çıkarılır. Standstill ve açık-yük
motor sağlığı PASS/FAIL değildir; kayıp/hatalı okuma hatasız sayılamaz.
Desteklenen diğer TMC'lerde 2208 hata bit maskesi uydurulmadan ham değer
gösterilir. TMC2660'ın READRSP seçiminde register yazımı gerektiğinden bu çip
eski pasif durum okumasında kalır. Fiziksel kabul üretilmez. M10 boş/gizli,
diğer ID'ler aynı numarada kalır.

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

Stepper başına ayrı M12 testi, gerekiyorsa başlangıçta bir kez onaylı XYZ
homing hazırlığından sonra seçilen ekseni güvenli rastgele konumlardan on kez
tek eksen olarak home eder ve Klipper faz kalibrasyonunu çalıştırır.
SAVE_CONFIG otomatik çalıştırılmaz. Hesaplanan bekleyen trigger_phase,
geri yüklenen G-code modları ve seçilmeyen eksenler (yalnız bir defalık
güvenli Z yükseltmesi hariç) kullanıcı incelemesinden önce doğrulanır.
Bekleyen yapılandırma tutulduğu için sonuç OBSERVED_USER,
restore_verified=false olur. Aynı stepper'ın bekleyen kalibrasyonu tekrar
çalışmayı engeller; diğer stepper'ın bekleyen sonucu engellemez.
M01/M12 cihaz bazlı katalog satırları ve uygun eski bilgi fallback'i korunur.
Yalnız fiziksel doğrulama kabul sağlayabilir.

## Son kapsam ve saha sırası
| ID | Sunulan |
|---|---|
| M01 | Ana fiziksel eksen switch'inde serbest/basılı/serbest; hedef bazlı |
| M02 | Sanal endstop'a elle basma pseudo-test'i bilerek gizli |
| M03 | Boş-yol onaylı, desteklenen yapılandırılmış XYZ homing |
| M04 | Ana Cartesian motor buzz; bağımsız çoklu Z/bağlı motor buzzing yok |
| M05 | Desteklenen koordinat XYZ 1 mm gidip dönüş |
| M06 | Harici gerçek 10 mm mesafe girişi ve ayrı onaylı dönüş |
| M07 | Homing öncesinde gerçek TMC register okuması; TMC2208 hata özeti; motor sağlığı PASS'i yok |
| M08 | Keşfedilmişse yalnız gerçekten raporlanan sürücü sıcaklığı |
| M09 | Raporlanan akım ayarı; ölçülmüş sargı akımı değil |
| M10 | Ayrılmış, gizli, boş ID; diğer numaralar kaydırılmadı |
| M11 | Motor enable bilgisi |
| M12 | Fiziksel stepper başına rastgele başlangıçlı on hedefli homing ve bekleyen faz kalibrasyonu; pasif last_home tanılaması |
| M13 | Mevcut angle sürücüsü sıcaklık durumu; mil açısı uydurulmaz |
| M14 | Komutlanan konum/homing/azami hız bilgisi |
| M15 | Uygulamaya özel sözleşme olmadan genel manual_stepper hareket adaptörü yok |
| M16 | Desteklenen raporlanmış carriage mod alanları; carriage aktivasyonu yok |
| M17 | Ham force/register yazma pseudo-test'i bilerek gizli |

Referans M fiziksel kabul çizelgesindeki 14 doğrulanmış hedefin adaptörü ve kullanıcı
kabulü korunur. Dört M07 sürücü hedefi fiziksel kabul çizelgesinin dışındaki
bilgilendirici Diagnostics kayıtlarıdır; fiziksel PASS sayılmaz. Diğer sürücü hata şemaları ve
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

M07 desteklenen sürücülerde homing veya motor enable gerektirmeden
register sorgular. Fiziksel çip/UART/SPI okunamıyorsa sonuç bilinmiyor/hata
olarak kalır; motor açma önerilmez ve PASS üretilmez.
M12 en son: mevcut stepper test girdisinde ilgili ekseni rastgele on
başlangıç konumundan home et, hesaplanan bekleyen trigger_phase değerini
incele ve kaydet. Başka stepper'ın bekleyen kalibrasyonu ikinci ekseni
engellemez; SAVE_CONFIG otomatik değildir. OBSERVED_USER metrolojik
hassasiyetin ölçüldüğü anlamına gelmez.

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

## Boş mesh ve gönderim öncesi ret düzeltmesi

17 Ekim `8bf95a8e7cc6431c99ede09170b26605` oturumunda M04/X hazırlık homing'i tamamlandı. HTTP ön kontrolünde profile_name boş ve mesh_min/mesh_max sıfırdı; abonelik gönderim guard'ı clear_mesh_before_motion_test ile reddetti (#295 rpc_guard_denied/guard_denied). Klipper'ın boş mesh temsili [[]], Python'da truthy olduğu için eski denetim bunu aktif matris sanıyordu. Artık hem küçük HTTP durumu hem dondurulmuş abonelik aynı kuralla denetlenir: açık boş profil, sıfır sınırlar ve matris varsa yalnız []/[[]] veya tuple eşdeğeri. Sayısal düz mesh, aktif/adsız mesh, eksik/bilinmeyen veri yine reddedilir. Yeni matris sorgusu veya mesh temizleme komutu yoktur.

Yalnız iletişim katmanının socket gönderiminden önce kesin olarak guard_denied işaretlediği ret, özgül BLOCKED sonucu verir; shutdown veya otomatik tekrar göndermez. Gönderilmiş, sunucu hatalı, zaman aşımına uğramış ya da belirsiz hareketin mevcut acil durdurma davranışı korunur. Hazırlık homing'i bu kayıtta doğrulandı; M04 fiziksel kabulü henüz yok.

## M12 sonuç önce, inceleme sonra

M12 on homing kalibrasyonunun sonucunu kullanıcı incelemesinden önce gösterir. Kullanıcı bekleyen faz, kaydedilmemiş yapılandırma ve modları zaman sınırı olmadan inceleyebilir. Eski M10 Self Test/inceleme akışı kaldırıldı. Sürücü hata bilgisi M07 Diagnostics altında pasif okunur; motor sağlığı PASS veya FAIL sonucu üretilmez.


## M12: seçili eksende on kez faz kalibrasyonu homing'i (17 Ekim 2026)

M12, keşfedilen fiziksel stepper başına zaten ayrı bir menü girdisidir; yeni
eksen seçim ekranı eklenmez. Gerekirse başlangıçtaki mevcut, onaylı XYZ
homing hazırlığı yalnız bir kez yapılır. Sonra seçilen eksen, güvenli
sınırlar içinde rastgele üretilmiş birbirinden farklı on konuma gider.
Her konumdan yalnız seçilen eksende G28 X, G28 Y veya G28 Z çalışır.
Bu on döngüde tüm eksenleri birlikte home eden yalın G28 kullanılmaz.
Sonunda ENDSTOP_PHASE_CALIBRATE STEPPER=... ile Klipper biriktirilmiş
faz istatistiklerinden sonuç hesaplar. SAVE_CONFIG otomatik çalışmaz.

XY hareketi için gerekli olduğunda Z başlangıçta yalnız bir kez 5mm güvenli
açıklığa yükseltilir; döngüler arasında yeniden Z homing yapılmaz.
Isıtıcı, mesh, güvenlik, G-code modları, fiziksel endstop ve test
sahipliği kontrolleri korunur. Başka stepper'ın bekleyen yapılandırma
değişikliği korunur; aynı hedefin bekleyen sonucu tekrar kalibrasyonu
engeller. Klipper'da CoreXY X/Y için bu kalibrasyon geçersizdir ve
reddedilir. Süre Moonraker'ın 900s RPC sınırına göre kontrol edilir.

Sonuç ekranı Homing cycles: 10 ve hesaplanan bekleyen trigger_phase
değerini gösterir. Bağımsız metrolojik doğruluk veya fiziksel kabul
iddiasında bulunmaz.

### M12 homing sonu endstop konumu düzeltmesi (17 Ekim 2026)

Fiziksel Y çalıştırmasında on homing içeren Klipper komutu tamamlandı; ancak
Klipper'ın bildirdiği Y konumu 6,825 mm, axis_minimum ise 7,0 mm idi.
Petrel'in genel sıkı eksen sınırı denetimi faz sonucu doğrulamasını
engelledi ve sonrasında doğrulama zaman aşımı emergency stop oluşturdu.
M12 artık **yalnız seçilen ve home edilmiş eksenin** fiziksel
position_endstop konumundan en çok yapılandırılmış bir motor tam-adımı
kadar ayrılmasını kabul eder. Diğer eksenler normal sınırlarında ve
beklenen konumlarında kalmalıdır. Sınır, yazıcıya özel sabit yerine
rotation_distance/full_steps_per_rotation ile hesaplanır.
Bilinmeyen veya sanal endstop geometrisi için bu istisna geçerli değildir.
Genel hareket/jog güvenlik sınırları değişmedi. RPC başarısı veya bu yazılım
düzeltmesi tek başına fiziksel kabul sayılmaz.
