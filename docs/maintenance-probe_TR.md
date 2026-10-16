# Maintenance prob akışları

[English](maintenance-probe.md)

P01/P02/P03/P04, P06 ve P12–P22 için somut adaptör vardır. P05 ve P07–P11 yalnız Leveling içinde kalır: prob offset kalibrasyonu, bütün bed-mesh işlemleri ve screws-tilt ayarı bilerek tekrarlanmaz.

Her seçim önce salt okunur ön kontrol yapar, ardından açık Start ister. Sonraki her eylem de dispatch öncesinde kuyruk ve bağlantı kanıtını yeniler. Homing ön koşuldur; otomatik yinelenmez. Hareket, yapılandırılmış firmware rutinlerini kullanır; bütün hareket yolunu açık tutun. Girişte soğuk, boşta ısıtıcılar ve bekleyen konfigürasyon bulunmaması gerekir. Kullanıcı sorularının zaman aşımı yoktur.

- P01 güncel QUERY_PROBE yanıtlarıyla bırakılmış → tetiklenmiş → bırakılmış geçişini ölçer.
- P02 LOAD_CELL_TEST_TAP ile tek fiziksel tap yakalar. 60 saniyelik firmware yakalaması yalnız Start sonrasında başlar; önceki soruda süre sınırı yoktur.
- P03 on örneğin min/max/aralık/ortalama/medyan/stddev verilerini, P04 ölçülen XYZ'yi kaydeder. Yalnız RPC başarısı ölçüm kanıtı veya PASS değildir.
- P06/P12/P16/P17/P18 yerel etkileşimli noktaları sınırlı TESTZ adımları, Accept ve açık iptal ile sunar. P12 ayrıca Adjusted sunar.
- P13/P14 firmware applied durumunu doğrular. P15/P16/P17/P18 ilgili bekleyen konfigürasyonu doğrular. Hiçbir akış SAVE_CONFIG göndermez.
- P19 BLTouch pinini açık eylemlerle çıkarır ve toplar; etkileşimden iptalle çıkarken önce toplama ister.
- P20 kalibre kuvveti ve açık yakalamalar arasındaki farkı kaydeder; kalibre olmayan ham veri gram sayılmaz.
- P21 CALC_MEASURED_SKEW öncesinde haricen ölçülmüş AC, BD ve AD girişlerini zorunlu tutar. Düzeltme uygulamaz.
- P22 firmware sıcaklık kayması kalibrasyonuna Next/Complete sağlar. Isıtıcı başlatmaz; dışarıdan ısıtma kullanıcının kontrolündedir.

Belirsiz aktif hareketin iptali Klipper emergency_stop ister. Firmware kalibrasyonu canlı kompanzasyonu değiştirebilir veya bekleyen konfigürasyon bırakabilir; akışı bitirmek geri alma iddiası değildir. CI fiziksel kabul kaydetmez. Testler yalnız imzalı branch HEAD üzerinde Driver Branch Regression ile çalışır.
