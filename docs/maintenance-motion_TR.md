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
