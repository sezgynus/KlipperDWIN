# Kurulum ve yapılandırma

[English](installation.md) · [Türkçe](installation_TR.md) · [Dokümantasyon](README_TR.md)

Bu belge Petrel'in arayüz restorasyonu geliştirme dalı `feature/graphite-theme` ile eşleşir; çalışma tamamlandığında `master` ile birleşecektir. Mevcut temiz `~/Petrel` kopyasında kurulumdan önce `git fetch origin` ve `git switch feature/graphite-theme` kullanabilirsiniz. Update Manager `master` izlediği için bu dalı korumak istediğiniz sürece onun güncelleme/kurtarma işlemlerini kullanmayın. Dalı koruyan adımlar [geliştirme dalını güncelleme](#geliştirme-dalını-güncelleme) bölümündedir.

## Kurulumdan önce

Uyumlu DWIN T5UIC1 panel, UART/GPIO erişimli Linux SBC, Python 3.11+ ve çalışan Klipper/Moonraker kurulumu kullanın. [LCD uyumluluğunu](lcd-assets_TR.md) kontrol edin. Kurulum betiği LCD kernel firmware'ini veya fontunu yüklemez; Petrel ikonlarını uygulama ilk LCD bağlantısında otomatik eşitler.

## Bağlantı ve seri port hazırlığı

| Ekran bağlantısı | Raspberry Pi bağlantısı |
|---|---|
| RX | GPIO14 / UART TX |
| TX | GPIO15 / UART RX |
| Encoder A | GPIO21 |
| Encoder B | GPIO19 |
| Encoder düğmesi | GPIO20 |
| VCC | 5 V |
| GND | GND |

GPIO numaraları **BCM numaralarıdır**. Encoder pinleri yapılandırma sırasında değiştirilebilir. Fiziksel bağlantılar için [bağlantı görsellerine](../images/) bakın.

`sudo raspi-config` içinde seri donanımı etkinleştirin, seri giriş konsolunu kapatın ve yeniden başlatın. Pi ve işletim sisteminizde GPIO14/15'i hangi UART aygıtının kullandığını doğrulayın. Kurulum `/dev/ttyS0` önerir; kendi kurulumunuza uygun aygıtı seçin.

## Kurulum

Servisin sahibi olacak kullanıcıyla çalıştırın. Repo temiz olmalı ve `~/Petrel` konumunda bulunmalıdır:

```bash
cd ~
git clone --branch feature/graphite-theme https://github.com/sezgynus/Petrel.git
cd ~/Petrel
./install.sh
```

Varsayılanı kabul etmek için Enter'a basın veya kendi değerinizi girin:

| Ayar | Kurulum varsayılanı |
|---|---|
| Moonraker URL | `http://127.0.0.1:7125` |
| UART | `/dev/ttyS0` |
| Encoder A/B | `21 19` |
| Encoder düğmesi | `20` |
| Moonraker güç aygıtı | `Printer` |
| Güç açma basılı tutma süresi | `2000` ms (2 saniye) |

Kurulum `~/petrel-env` ortamını hazırlar, bağımlılıkları yükler ve `Petrel.service` servisini etkinleştirir. Ayarlar `~/.config/Petrel/Petrel.env` içinde tutulur; `moonraker.conf` yanına `Petrel.conf` include dosyası eklenir ve servis Moonraker güncellemelerine kaydedilir. Kurulum tekrarlandığında mevcut ayarlar korunur.

Moonraker yapılandırmanız farklı konumdaysa:

```bash
MOONRAKER_CONFIG=/path/to/moonraker.conf ./install.sh
```

## LCD kaynakları ve ilk açılış

1. [LCD fontunu kurun](lcd-assets_TR.md#lcd-fontu). Font SD karttan bir kez yüklenir; ikonlar ve açılış görseli UART üzerinden otomatik yönetilir.
2. Petrel açılış ilerlemesi tamamlanıp **Home** görünene kadar bekleyin.
3. Enkoderi çevirip bir menü açın; sıcaklıkların web arayüzüyle uyuştuğunu kontrol edin.
4. Yazılar/ikonlar yanlışsa [LCD kaynak rehberini](lcd-assets_TR.md), bağlantı hatası varsa aşağıdaki sorun giderme tablosunu izleyin.

Moonraker, Petrel bağlantısına izin vermelidir. Kimlik doğrulama gerekiyorsa `MOONRAKER_API_KEY` ayarlayın. Seri port ve GPIO erişimi için servis kullanıcısının izinlerini kontrol edin; installer `dialout` ve `gpio` gruplarını yapılandırır.

## Ayarları değiştirme

```bash
cd ~/Petrel
./configure.sh
```

Mevcut değerler soruların varsayılanı olur. Özel `PETREL_SETTINGS_FILE` yolu ve yapılandırıcının sormadığı font/socket/görüntü klasörü dahil diğer ortam ayarları korunur; aynı anahtar tekrar eklenmez. Dosya özel izinlerle atomik olarak yenilenir. Kaydettikten sonra değişiklikleri uygulamak için sunulan servis yeniden başlatmasını kabul edin. Ekran parlaklığı/kısma ayarları burada değil, LCD'de **Home → Display** altında yapılır.

Yapılandırıcının sormadığı ayarlar için harici ortam dosyasını düzenleyin. `export` kullanmadan düz `KEY=value` satırları yazın:

| Ayar | Amaç / varsayılan |
|---|---|
| `MOONRAKER_URL` | Moonraker adresi / `http://127.0.0.1:7125` |
| `MOONRAKER_API_KEY` | Gerekiyorsa kimlik doğrulama anahtarı / boş |
| `PETREL_REQUEST_TIMEOUT` | Saniye cinsinden istek zaman aşımı / `5` |
| `PETREL_SERIAL_PORT` | Yapılandırılmış UART / kurulum `/dev/ttyS0` önerir |
| `PETREL_ENCODER_PINS` | BCM numaralarıyla encoder A/B / `21 19` |
| `PETREL_BUTTON_PIN` | BCM numarasıyla encoder düğmesi / `20` |
| `PETREL_SETTINGS_FILE` | Yerel preset yedeği / `~/.config/Petrel/presets.json` |
| `PETREL_POWER_DEVICE` | Moonraker güç aygıtınızın adı / `Printer` |
| `PETREL_POWER_ON_HOLD_MS` | Milisaniye cinsinden güç açma süresi / `2000`; `0` anında açar |
| `PETREL_EMULATOR` | Ekran görüntüsü alma / `0` kapalı, `1` açık |

Düzenleme sonrası `sudo systemctl restart Petrel.service` ile yeniden başlatın. Özel anahtarları ve makine ayarlarını takip edilen repo dosyalarının dışında tutun. Görüntü almaya özel seçenekler için [emülatör rehberine](ui-emulator_TR.md) bakın.

## Güncelleme

### Geliştirme dalını güncelleme

`feature/graphite-theme` kullanırken Update Manager/Info güncelleme veya kurtarması yerine bu yolu izleyin. Yazıcıyı boşta bırakın; takip edilen değişiklikleri ve eklediğiniz dosyaları ayrı yere kaydedin. Önce şunları kontrol edin:

```bash
cd ~/Petrel
git status --short
git branch --show-current
```

`git status --short` çıktısı boş olmalı. Ardından dalı seçip servisi durdurun; güncellemeyi yalnız ileri yönde alın, installer ile bağımlılık/servis kaydını yenileyin ve çalışan servisi yeniden başlatın:

```bash
git switch feature/graphite-theme &&
sudo systemctl stop Petrel.service &&
git pull --ff-only origin feature/graphite-theme &&
./install.sh &&
sudo systemctl restart Petrel.service
```

Bir adım başarısız olursa sonraki adımlar çalışmaz; dosyaları zorla sıfırlamayın. Servis durdurulmuş olabilir: sebebi giderip tamamladıktan sonra yeniden başlatın. Kontrol için `sudo systemctl status Petrel.service --no-pager` kullanın. Özel ortam ayarları korunur; ikonlar ilk LCD bağlantısında güncellenir, font ayrıca değiştiyse [LCD fontu](lcd-assets_TR.md#lcd-fontu) adımını tekrarlayın.

Dal `master` ile birleşince temiz checkout’ta `git fetch origin` ve `git switch master` kullanarak normal güncelleme yoluna dönün; bu geçici dal notları da aynı birleşmede kaldırılmalıdır.

### Normal güncelleme ve eski kurulumdan geçiş

Mevcut kurulum, sonraki Moonraker güncellemesinden sonra otomatik taşınır: eski updater bu sürümü indirir ve ilk servis açılışı ayrı bir geçiş işi başlatır. Ayarlar korunur, repo `~/Petrel` konumuna taşınır, `~/petrel-env` hazırlanır, `Petrel.service` kurulur ve Moonraker yeni updater kaydıyla yeniden başlatılır. Python bağımlılıkları için birkaç dakika bekleyin. Otomatik geçiş Pi üzerinde şifresiz sudo erişimi gerektirir; bu yoksa bir kez `sudo python3 ~/KlipperDWIN/petrel_migration.py --user "$USER"` çalıştırın. Mevcut bir Petrel kurulumunun üzerine yazılmaz. Servis geçişi başarısız olursa önceki kurulum geri yüklenir; ayrıntılar `journalctl -u Petrel-migration.service` içindedir.

`master` kurulumunda, Moonraker yapılandırmasını yeniden okuduktan sonra **Mainsail → Machine → Update Manager → Petrel** yolunu kullanın. Listeyi yenileyip güncelleyin; bağımlılıklar ve servis yeniden başlatması otomatik yapılır. Update Manager `master` dalını takip eder.

Yazıcı boşta iken LCD'deki **Info** bölümünden de Petrel güncellemelerini kontrol edip yükleyebilirsiniz. [Info ve güncellemeler](user-guide_TR.md#info-ve-güncellemeler) bölümüne bakın. Takip edilen repo dosyalarındaki yerel değişiklikler güncellemeyi engelleyebilir; kurtarma bunları silmeden önce inceleyin veya yedekleyin.

## Sorun giderme

```bash
sudo systemctl status Petrel.service --no-pager
journalctl -u Petrel.service --since "10 minutes ago" --no-pager
sudo systemctl restart Petrel.service
```

| Belirti | Kontrol edilecekler |
|---|---|
| Ekran boş veya sürekli yeniden bağlanıyor | Panel gücü, çapraz TX/RX, seçilen UART, seri giriş konsolu ve izinler |
| Encoder yanıt vermiyor | BCM pin ayarları ve bağlantılar |
| Açılış bir aşamada kalıyor | Klipper/Moonraker hazır durumu, ekran kaynakları ve servis günlükleri |
| İsteğe bağlı menü yok veya kilitli | Gerekli Klipper/Happy Hare yapılandırması, bağlantı ve mevcut yazıcı durumu |
| Önizleme görseli veya metadata yok | Slicer thumbnail'ları ve Moonraker'daki metadata |
| Wi-Fi bilgisi kullanılamıyor | Kablosuz bağlantı ve Linux `iw` komutunun bulunması |
| Güncelleme engelleniyor | Yerel repo değişiklikleri ve Moonraker Update Manager durumu |
| İşlem başarısız veya zaman aşımına uğradı | Tekrarlamadan önce Mainsail'den gerçek yazıcı durumunu kontrol edin |

Hata bildirimine yazılım revizyonunu, Pi/işletim sistemini, ilgili yapılandırmayı ve günlük bölümünü ekleyin. Görsel sorunlarda fotoğraf veya [emülatör ekran görüntüsü](ui-emulator_TR.md) ekleyin; paylaşmadan önce kimlik bilgilerini kaldırın.
