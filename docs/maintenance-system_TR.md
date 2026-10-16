# Maintenance sistem tanılamaları

[English](maintenance-system.md)

S01–S10 gerçek host, disk, MCU, CAN, sınıflandırılmış yakın olaylar ve kaydedilmiş baskı geçmişini okur. MCU adları ayrı kalır; null CAN alanı arıza sayılmaz. S04 yalnız açık istekte tek dizin listeler; dosya adlarını değil disk toplamlarını tutar. S09 ham konsol satırı veya token yerine olay/hata sayıları ve bilinen hata kategorilerini tutar. S19 yenileme veya kurulum yapmadan güncelleme durumunu okur; normal güncelleme kontrolleri Info'da kalır.

S11 gerçek yöntem, zaman, cihaz, planlanan epoch/config işareti, firmware/config kimliği ve izinli kanıtla en fazla 64 sonuç saklar. CI fiziksel kabul değildir. S12 sınırlı örneklenmiş alt-sınır ısıtıcı/fan ON süresi kaydeder: yalnız iki uçta da ON olan <=2 sn aralıklar sayılır. Eksik örnekler, kesinti ve çökme kayıpları ömür boyu saat gibi uydurulmaz. Envanter epoch bazında önbelleklidir; normal tick I/O yapmaz. Yazma mevcut worker'ı kullanır.

S13 konum farkı toplamı yerine yetkili bir eklenti sayacı ister. ~/.config/Petrel altında maintenance-travel-counter.json içine {"version":1,"object":"your_registered_object","authoritative":true} beyan edilir; kayıtlı nesne mm cinsinden negatif olmayan x_mm/y_mm/z_mm sayaçlarını döndürmelidir. Bu kaynak yoksa özellik gizli kalır.

S14 güncel sürücü/UART epoch'u kapsamında gerçek TX/RX, handshake isteği, yanıt zaman aşımı, CRC bildirimi ve sınırlı RX atmalarını gösterir. CRC bildirimi panel protokol olayıdır, optik kontrol değildir. S15 fiziksel GPIO çevirme adımı ve buton kenarlarını sayar; uzaktan girdiler bu sayaçları artırmaz. Yönlendirmeli testi Start sonrasında iki yönde yeni fiziksel adım ve yeni fiziksel buton kenarı ister; yalnız sayaç okumak PASS üretemez. GPIO callback'inde yazıcı snapshot'ı alınmaz.

S16 fiziksel LCD'de açık ilerletilen kırmızı/yeşil/mavi/beyaz/siyah gözlem alanları ve açılış kaynak eşitleme bilgisi sunar. S17 açık ilerletilen %10/%50/%100 arka ışık seviyeleri sunar ve yakalanmış çalışma anı parlaklığına döner. Ayarlar kaydedilmez. Otomatik karartma yalnız sahipli panel akışında askıya alınır. Kullanıcı sorusu zaman aşımına uğramaz; yeniden bağlanan panele eski oturum parlaklık komutu sessizce uygulanmaz.

S20 açık eylemle ~/.config/Petrel/maintenance-report.json yazar. Remote Display mevcut Host/Origin sınırları içinde /maintenance-report.json yolundan son çıktıyı indirir. İndirme rapor üretmez veya test başlatmaz. Ham konfigürasyon, dosya adı, URL veya API anahtarı dışa aktarılmaz.

Bütün okumalar/ön kontroller sınırlı ve asenkrondur. Fiziksel panel gözlemleri gerçek yazıcı kabulünü bekler.
