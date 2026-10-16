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
