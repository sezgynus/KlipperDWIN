# Klipper kurtarma
Petrel, Moonraker erişimini Klipper'ın hazır olmasından ayırır. MCU shutdown veya
Klipper yapılandırma hatasında LCD, çıkışsız "Moonraker unavailable" yazısı yerine
Klipper'ın state_message metnini (MCU adı dahil) ve kaydırılabilir ayrıntıları gösterir.

- Refresh connection yalnız durum okur; yeniden başlatma yapmaz.
- Restart Klipper, POST /printer/restart ile host/yapılandırmayı yeniden yükler.
- Firmware Restart, POST /printer/firmware_restart ile Klipper ve bağlı MCU'ları sıfırlar.
- Klipper bağlantısı kopmuşsa Restart Klipper service yalnız /machine/system_info
  içindeki instance_ids.klipper ve available_services bu örneğin tam servis adını
  doğruladığında sunulur. Servis adı tahmin edilmez.
- Moonraker gerçekten erişilemiyorsa bağlantı yenileme bilgisi gösterilir.
  Erişilemeyen API üzerinden Moonraker yeniden başlatılamaz.
- Klipper starting/ready durumundaysa eski hata ekranından restart sunulmaz.

Restart düğmesi tek açık basışla çalışır. Başlangıç seçimi salt-okunur Refresh
kontrolüdür. Önce yazıcıyı kontrol edin ve hatanın nedenini giderin. Komutlar mevcut HTTP komut worker'ında,
gönderimden hemen önce taze sunucu/yazıcı kontrolüyle yürütülür. İstek onayı
READY kanıtı değildir; mevcut aboneliğin toparlanması beklenir. Başarısız veya
belirsiz komutlar otomatik tekrarlanmaz. Kurtarma Home'a döner; kesilen ısıtma,
hareket, baskı veya Maintenance testi devam ettirilmez. Termal güvenlik sınırları
değiştirilmez.

Offline kontroller mevcut sınırlı okuma worker'ında en çok bir bekleyen iş tutar;
tamamlandıktan sonra iki saniye aralıkla yeniden denenir. Yeni thread veya
transport oluşturulmaz. Normal READY çalışmada kurtarma okuması yapılmaz.
Petrel açılırken Klipper zaten hatalıysa da kurtarma menüsü gösterilir.
Klipper hazır değilken encoder ile ekran kullanılabilir.

Regresyonlar durum/hata ayrımını, MCU metnini, doğru servis seçimini, taze dispatch
guard'ını, yinelenen/belirsiz komutları, ayrı onayı, kaydırmayı, soğuk açılışı ve
kurtarma gezinmesini kapsar. Yalnız CI kullanılır; lokal test veya emülatör
çalıştırılmadı. Fiziksel kabul bekliyor.

Hata düz çok satırlı metin alanında, düğmeler sabit alt bölümde gösterilir. İlk düğmenin soluna dönerek hata metnine odaklanılır; encoder kaydırır, basış düğmelere döndürür. Satır sonları LCD ASCII dönüşümünden önce ayrılır; soru işaretine dönüşmez. Restart uçlarına null yerine boş JSON nesnesi gönderilir. Başarısız isteğin temizlenmiş transport hatası gösterilir. Ek onay menüsü açılmaz.
