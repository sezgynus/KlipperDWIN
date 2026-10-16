# Hareket Maintenance
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

## Salt hareket sözleşmesi (henüz üretim adaptörü değil)
Cartesian/CoreXY koordinat hareketi gerçek XYZ homing, yapılandırılmış sınırlar,
soğuk/OFF ısıtıcılar, açık ana motorlar ve açık boş-yol onayıyla sınırlıdır.
M04 yalnız ana Cartesian motorlarda Klipper'ın 10 çevrimlik 1 mm STEPPER_BUZZ
komutunu kullanır; bağımsız çoklu Z ve bağlı motor buzzing kabul edilmez.
M05 en çok 5 mm/sn XY / 1 mm/sn Z ile 1 mm gidip dönme derler. M06 tek
10 mm ileri hareket derler; ayrı onaylı dönüş aynı ölçüm durağı konumunu ister.
Hareket öncesine gizlice homing eklenmez. XYZ sınırlarında 2 mm pay; XY için
en az 5 mm Z açıklığı gerekir. Yüklü mesh/bilinmeyen dönüşüm, carriage ve
override edilmiş protokol komutları kapatılmak yerine testi engeller.
Benzersiz SAVE/RESTORE_GCODE_STATE MOVE=0 modal ayarları korur; M400 hareket
bitimini bekler. FORCE_MOVE, SET_KINEMATIC_POSITION ve ayar yazımı yoktur.
M03 açıkça seçilen yapılandırılmış XYZ homing'dir; homing_override/macro G28
reddedilir. M12 yalnız yapılandırılmış fiziksel endstop phase, gerçek last_home
geçmişi ve bekleyen config yokken derlenir; kaydetmeden trigger_phase bekletir.
Yazılım geri okuması fiziksel konum kanıtı değildir. Bunlar salt sözleşmelerdir;
controller/UI kayıtları CI sonrasında ayrı değişiklikle gelir.

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
ile gir (0,1 mm adımlar); başlangıçtaki 10 mm yalnız değiştirilebilir öneridir,
açık operatör girişi/onayı olmadan kabul edilmez. Ters hareketten önce yeni
ön kontrol ve ayrı Return to start onayı gerekir. Sabit ölçüm ve dönüş onayı
ekranları süresizdir. Değişmiş konum/mod, kapalı motor veya kayıp homing,
tahmin edilmek yerine dönüşü engeller. Sabit aşamada iptal arabayı ölçüm
durağında bırakır; otomatik dönüş yapmaz, geri yükleme false bildirilir.
En çok 0,2 mm hata + doğrulanmış dönüş/kullanıcı gözlemi bu sınırlı tanılamayı
geçirir; rotation_distance değişmez. Bu kullanıcı bildirimi ölçümüdür;
kalibre metroloji iddiası değildir.

M12 bir yapılandırılmış fiziksel endstop stepper'ı için mevcut Klipper homing
geçmişini kullanır. Otomatik homing ve SAVE_CONFIG yoktur. Tam hedefin bekleyen
trigger_phase sonucu, korunmuş mod/konum ve sonra kullanıcı gözlemi gerekir.
Bekleyen kalibrasyon config'i bilerek geri alınmadığı için sonuç OBSERVED_USER,
restore_verified=false olur. Önceden bekleyen config başlangıcı engeller.
M01 ve M12 katalog kapsamları cihaz satırlarını destekler; cihaz bazlı kanıt
yokken eski global bilgi fallback'i korunur. Uygulama ve CI fiziksel kabul vermez.
