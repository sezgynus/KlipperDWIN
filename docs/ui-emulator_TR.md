# Emülatör ekran görüntüleri

[English](ui-emulator.md) · [Türkçe](ui-emulator_TR.md) · [Katkı](../CONTRIBUTING_TR.md)

## Ne işe yarar

İsteğe bağlı emülatör, çalışan Petrel servisinin çizdiği ekranları yakalar. Yerleşimleri incelemek, dokümantasyonu yenilemek ve görsel hataları özgün boyutlu görsellerle bildirmek için kullanın. Gerçek LCD arayüzünü takip eder; bağımsız yazıcı simülatörü değildir. İsteğe bağlı canlı tarayıcı görüntüleme aşağıda anlatılmıştır. Fiziksel encoderle gezinin, ardından SSH üzerinden görüntü isteyin.

## Açma veya kapatma

Bağımlılıklar normal kurulum ve Moonraker güncellemelerine dahildir. `~/.config/Petrel/Petrel.env` içinde varsayılanı değiştirin:

```ini
PETREL_EMULATOR=1
```

Ardından yeniden başlatın:

```bash
sudo systemctl restart Petrel.service
```

Kapatmak için `PETREL_EMULATOR=0` yapıp yeniden başlatın. Kurulum/yapılandırma tekrarlandığında mevcut açık değer korunur. `./configure.sh`, özel font, socket ve ekran görüntüsü klasörü anahtarlarını da korur. Eski kurulumda bağımlılıklar eksikse:

```bash
cd ~/Petrel
~/petrel-env/bin/python -m pip install -r requirements.txt
```

## SSH üzerinden görüntü alma

1. LCD'de istediğiniz ekranı açın ve çizimin bitmesini bekleyin.
2. SSH içinde **servis kullanıcısıyla, sudo kullanmadan** çalıştırın:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py
```

Komut kayıt yolunu yazdırır. Görseller varsayılan olarak `~/Petrel-screenshots/` içine zaman damgalı, benzersiz adlarla kaydedilir. Çıktı yeniden boyutlandırılmamış, kayıpsız **272×480 RGB PNG**'dir. Otomatik görüntü kaydedilmez.

BMP çıktısı için:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --format bmp
```

İncelemek için görselleri bilgisayarınıza kopyalayın. Repo ekran görüntüleri, ekranı/durumu anlatan adlarla `docs/assets/screens/` içine konur.

## Ek ayarlar

Aynı harici ortam dosyasına yazıp servisi yeniden başlatın:

| Değişken | Amaç |
|---|---|
| `PETREL_SCREENSHOT_DIRECTORY` | Özel çıktı klasörü |
| `PETREL_EMULATOR_SOCKET` | Özel yerel görüntü soketi; varsayılan `~/.cache/Petrel-emulator/control.sock` |
| `PETREL_EMULATOR_FONT` | Özelleştirilmiş fiziksel panelle eşleşen font dosyası |

Özel sokette görüntü komutuna aynı yolu verin:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --socket /path/to/control.sock
```

## Sorun giderme ve sınırlar

| Sorun | Yapılacak işlem |
|---|---|
| Bağlanamıyor veya izin reddediliyor | `PETREL_EMULATOR=1` kontrol edin, servisi yeniden başlatın, servis kullanıcısıyla çalıştırın ve soket yolunu kontrol edin |
| Görüntü reddediliyor | Panel bağlantısını, yüklenen kaynakları ve servis günlüğünü kontrol edin; tamamlanmış ekranı bekleyin |
| Yazı/ikonlar panelden farklı | Font/ikon dosyalarını karşılaştırın; [emülatör kaynaklarına](../assets/emulator/README_TR.md) bakın |
| Kısma görselde görünmüyor | Görüntüler fiziksel arka ışık parlaklığını değil ekran piksellerini gösterir |

Emülatör LCD belleğini okumak yerine çizim komutlarını takip eder. Fontlar, JPEG çözümü ve QR deseni fiziksel panelden farklı olabilir. Bu sorunlarda hem ekran görüntüsü hem fotoğraf paylaşın; tek başına görüntü fiziksel ekran doğruluğunu kanıtlamaz.

## Dokümantasyon ekranlarını çevrimdışı üretme

Bir geliştirme checkout’u içinde tüm dokümantasyon ekranlarını gerçek UI çizimleriyle yeniden üretebilirsiniz. Aracın örnek yazıcı ve MMU verileri kullandığı bu işlem fiziksel yazıcıya bağlanmaz; çalışan servis veya UART bağlantısı gerektirmez. Normal kurulum bağımlılıkları yeterlidir; repodaki `tests/` klasörü bulunmalıdır.

```bash
cd ~/Petrel
~/petrel-env/bin/python tools/render_docs_screenshots.py --frame
```

Tüm ekranlar başarılı çizilirse `docs/assets/screens/` içindeki görseller yenilenir. Mevcut dosya adlarını koruyun; forumlar bu adlara dış bağlantı verebilir. Yeni bir ekran eklemek için aracın sahne listesine örnek durumu ve iki dilde açıklamasını ekleyin. Galerileri de aynı listeden yeniden üretir.

Repo dosyalarını değiştirmeden incelemek için:

```bash
~/petrel-env/bin/python tools/render_docs_screenshots.py --output-directory /tmp/petrel-docs-screens
```

Örnek değerleri ve kullanılabilir ekranları [galeride](screenshots_TR.md) görebilirsiniz. Gerçek bir hatayı raporlarken yukarıdaki canlı servis yakalama yöntemini kullanın.

İsteğe bağlı `--frame`, ekran görüntüsünü fiziksel ekran çerçevesinin içine yerleştirir. Parametre verilmezse 272×480 çıktı değişmez.

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --frame
```

### PNG, çerçeve ve GIF yenileme

Tek üretim oturumunda aynı checkout'tan bütün çıktıları yenileyin:

```bash
~/petrel-env/bin/python tools/render_docs_screenshots.py --frame
~/petrel-env/bin/python tools/render_print_controls.py
~/petrel-env/bin/python tools/render_print_controls.py --frame
~/petrel-env/bin/python tools/render_docs_workflows.py
```

İlk komut özgün 272×480 panel PNG'lerini ve `docs/assets/screens/framed/` içindeki 528×900 sunum kopyalarını üretir; aynı UI pikselleri çerçeveye yeniden örneklenmeden yerleştirilir. İki galeri aynı sahne kaydından, aynı menü sırasıyla yenilenir. Repo içindeki varsayılan hedefe üretirken `--frame` yazılmasa da çerçeveli kopyalar yenilenir. Bütün sahneler ve çerçeveler hazırlanıp başarıyla tamamlanmadan mevcut panel dosyaları değiştirilmez. Özel `--output-directory` hedefi ise yalnız `--frame` istenirse çerçeve üretir. Mevcut 76 dosya adı korunur; yeni sahneler eklenir.

İkinci/üçüncü komut Print/Tune başarı akışını özgün/çerçeveli GIF olarak üretir. Son komut güç basılı tutma/iptal/engelleme, iki kırmızı ret yanıp sönmesi, uzun MMU hatası kaydırması ve 0/1/50/100% panel-native fan animasyonu için iki biçimde GIF üretir. Özgün GIF'ler `docs/assets/`, sunum kopyaları `docs/assets/framed/` içindedir. PNG komutu bu GIF'leri yenilemez.

Bütün durumlar gerçek UI/driver ile örnek verilerden üretilir; fiziksel yazıcıya bağlanılmaz. Hata yanıtları test doubles ile sağlanır. Saat 12:34'tür; animasyonlar kontrollü geçen zamanla örneklenir. Eksik preview/katman, azaltılmış Tune ve uzun hata örnekleri galeriye dahildir. Fan GIF'i panel animasyon komutlarını emüle eder; fiziksel JPEG decoder doğrulaması yerine geçmez.


## İsteğe bağlı canlı Remote Display (8088 portu)

Petrel, LCD framebuffer'ını küçük bir HTTP sunucusuyla canlı sunabilir ve sanal enkoder girişlerini kabul eder: mouse tekerleği enkoderi döndürür, orta tuş ENTER üretir. Ekrandaki **CCW**, **Enter** ve **CW** butonları, dokunmatik ekranlar dahil aynı girişleri sağlar. Her döndürme butonu tıklaması enkoderi bir adım ilerletir. Gerçek LCD ve enkoder de çalışmaya devam eder.

`~/.config/Petrel/Petrel.env` dosyasında etkinleştir:

```ini
PETREL_REMOTE=1
PETREL_REMOTE_PORT=8088
```

Varsayılan dinleme adresi artık **`0.0.0.0:8088`**, yani bütün IPv4 ağ arayüzleridir. `PETREL_REMOTE_HOST=0.0.0.0` satırı isteğe bağlıdır (zaten varsayılan). Feature sürümü çalışırken yerel ağdan **`http://<PI_LAN_IP>:8088`** veya Tailscale üzerinden **`http://<PI_TAILSCALE_IP>:8088`** adresini açabilirsin. SSH tüneli veya Tailscale Serve gerekmez. Tailscale IP'si `tailscale ip -4` ile öğrenilebilir.

Açık internetten erişim için ayrıca **dışarıdan erişilebilir bir IP/adres ve modemde TCP 8088 port yönlendirmesi veya dışarıya açık başka bir ağ geçidi** gerekir; sadece `0.0.0.0` dinlemek NAT veya güvenlik duvarını aşmaz.

**Güvenlik:** Bu küçük sunucuda şu anda **parola, giriş ekranı veya HTTPS yoktur**. TCP 8088 portuna ulaşabilen herkes LCD'yi görebilir ve enkoder üzerinden yazıcıyı kontrol edebilir. Bu riski açıkça kabul etmeden portu genel internete yönlendirme. Tarayıcı kaynak kontrolleri kimlik doğrulama değildir.

Sunucu isteğe bağlıdır; `PETREL_REMOTE` kapatılıp Petrel yeniden başlatıldığında dinleme durur. Daha dar erişim tercih edilirse `PETREL_REMOTE_HOST=tailscale` (sadece mevcut Tailscale IPv4) veya `PETREL_REMOTE_HOST=127.0.0.1` (yalnız Pi) kullanılabilir. Ayarları değiştirdikten sonra yazıcı boşta iken Petrel'i yeniden başlat. `PETREL_REMOTE=1` emülatörü otomatik açar.

Görüntü kareleri istek üzerine yaklaşık 4 FPS hızında, 272×480 boyutunda üretilir; sanal enkoder girişleri fiziksel girdilerle aynı oturum kontrollü UI olay kuyruğundan geçer. Uzaktan orta tuşu basılı tutmak güç uzun basışını bilerek tetiklemez. Ekran tek başına fan, LED veya buzzer'ın fiziksel çalıştığını doğrulamaz.
