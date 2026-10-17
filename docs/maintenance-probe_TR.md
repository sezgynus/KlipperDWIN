# Maintenance prob akışları

[English](maintenance-probe.md)

P01/P02/P03/P04, P06 ve P12–P22 için somut adaptör vardır. P05 ve P07–P11 yalnız Leveling içinde kalır: prob offset kalibrasyonu, bütün bed-mesh işlemleri ve screws-tilt ayarı bilerek tekrarlanmaz.

Her seçim önce salt okunur ön kontrol yapar, ardından açık Start ister. Sonraki her eylem de dispatch öncesinde kuyruk ve bağlantı kanıtını yeniler. Homing ön koşuldur; otomatik yinelenmez. Hareket, yapılandırılmış firmware rutinlerini kullanır; bütün hareket yolunu açık tutun. Girişte soğuk, boşta ısıtıcılar ve bekleyen konfigürasyon bulunmaması gerekir. Kullanıcı sorularının zaman aşımı yoktur.

- P01 servo adı/açı varsaymaz. Moonraker'ın güncel `configfile.settings.probe.activate_gcode` ve `deactivate_gcode` alanlarındaki (veya uygun `bltouch` bölümündeki) düz G-code metnini aynen okur. Kullanıcı Start onayından sonra aktivasyon G-code'u değiştirilmeden gönderilir, ardından `QUERY_PROBE` çalışır. Kullanıcı probu tetikleyip bırakırken iki yeni `QUERY_PROBE` okuması yapılır; `open → TRIGGERED → open` doğrulandığında tanımlı deaktivasyon G-code'u aynen gönderilir. PASS için deaktivasyon RPC'sinin tamamlanması gerekir. Aktivasyondan sonra iptal de önce deaktivasyon, ardından ABORTED sonucunu verir. Petrel eksen hareketi veya SAVE_CONFIG eklemez. G-code içindeki hareketlerden kullanıcı yapılandırması sorumludur; Klipper'ın önerdiği gibi prob hazırlama/toplama G-code'larında toolhead hareketi olmamalıdır. İki alan birlikte tanımlı veya ikisi de boş olmalıdır. Jinja şablonu doğrudan Moonraker G-code komutu olarak çalıştırılamayacağı için güvenli biçimde engellenir. Komut başarısız/belirsizse servo geri yüklemesi ispatlanamaz ve fiziksel PASS verilmez.
- P02 LOAD_CELL_TEST_TAP ile tek fiziksel tap yakalar. 60 saniyelik firmware yakalaması yalnız Start sonrasında başlar; önceki soruda süre sınırı yoktur.
- P03 on örneğin min/max/aralık/ortalama/medyan/stddev verilerini, P04 ölçülen XYZ'yi kaydeder. P04 başladığında homing doğrulanmış ancak Z güvenli sınırın altındaysa, kullanıcı Start onayı aynı zamanda yalnız Z ekseninin 10 mm güvenli yüksekliğe (veya Z maksimumundan güvenli pay bırakılan üst sınıra) kontrollü kaldırılmasını kapsar. Hareket sınırlı ve düşük hızlı göreli Z komutuyla yapılır; G-code modu kaydedilip geri yüklenir ve M400 tamamlanır. Yeni XYZ/mod geri okuması hareketi doğrulamazsa PROBE çalışmaz. Doğrulama başarılıysa yeni güvenlik ön kontrolünden sonra PROBE başlar; eksenler yeniden home edilmez. Z zaten yeterince yüksekse kaldırma yapılmaz. Yalnız RPC başarısı ölçüm kanıtı veya PASS değildir.
- P06/P12/P16/P17/P18 yerel etkileşimli noktaları sınırlı TESTZ adımları, Accept ve açık iptal ile sunar. P12 ayrıca Adjusted sunar.
- P13/P14 firmware applied durumunu doğrular. P15/P16/P17/P18 ilgili bekleyen konfigürasyonu doğrular. Hiçbir akış SAVE_CONFIG göndermez.
- P19 BLTouch pinini açık eylemlerle çıkarır ve toplar; etkileşimden iptalle çıkarken önce toplama ister.
- P20 kalibre kuvveti ve açık yakalamalar arasındaki farkı kaydeder; kalibre olmayan ham veri gram sayılmaz.
- P21 CALC_MEASURED_SKEW öncesinde haricen ölçülmüş AC, BD ve AD girişlerini zorunlu tutar. Düzeltme uygulamaz.
- P22 firmware sıcaklık kayması kalibrasyonuna Next/Complete sağlar. Isıtıcı başlatmaz; dışarıdan ısıtma kullanıcının kontrolündedir.

Belirsiz aktif hareketin iptali Klipper emergency_stop ister. Firmware kalibrasyonu canlı kompanzasyonu değiştirebilir veya bekleyen konfigürasyon bırakabilir; akışı bitirmek geri alma iddiası değildir. CI fiziksel kabul kaydetmez. Testler yalnız imzalı branch HEAD üzerinde Driver Branch Regression ile çalışır.

## Eksik homing hazırlığı

XYZ hareketi gerektiren testlerin ilk ön kontrolünde eksenler home edilmemişse test yalnız bu nedenle sonlandırılmaz. `Home XYZ, then run test` onayından sonra ortak güvenlikli homing hazırlığı yürür; iki taze XYZ/mod okuması doğrulanınca aynı test yeni ön kontrolle otomatik devam eder. Hata/aktif iptal asıl testi başlatmaz. Bilgi/sensör okuma testleri homing yapmaz; Leveling'deki hariç tutulan özellikler bu değişiklikle Maintenance'a eklenmez. Hareket profili, soğuk/OFF ısıtıcılar, konum/açıklık ve diğer güvenlik koşulları korunur.
