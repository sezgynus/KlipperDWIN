# KlipperDWIN

**DWIN ekranınız için yerel Klipper kontrol paneli.**

Döner encoder ile dosyaları gezinin, başlatmadan önce baskıyı inceleyin, yazıcıyı ayarlayın ve tabla kalibrasyonu yapın.

<p align="center">
  <a href="README.md">English</a> · <a href="README_TR.md">Türkçe</a>
</p>
<p align="center">
  <a href="https://github.com/sezgynus/KlipperDWIN/tree/v1.0.0"><img alt="v1.0.0" src="https://img.shields.io/badge/version-v1.0.0-0969da"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white">
  <img alt="Klipper / Moonraker" src="https://img.shields.io/badge/Klipper-Moonraker-7d3cff">
  <a href="LICENSE"><img alt="GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
</p>
<p align="center">
  <img src="docs/assets/screens/home.png" width="240" alt="Home">
  <img src="docs/assets/screens/print-preview.png" width="240" alt="Print preview">
</p>

[Özellikler](#özellikler) · [Kurulum](#kurulum) · [Arayüz rehberi](#arayüz-rehberi) · [Yapılandırma](#yapılandırma) · [Sorun giderme](#sorun-giderme) · [Geliştirme](#geliştirme)

KlipperDWIN, Raspberry Pi veya uyumlu bir Linux SBC üzerinde çalışır. **272×480 DWIN T5UIC1 ekrana** UART üzerinden bağlanır, encoder girdilerini GPIO üzerinden okur; yazıcı komutları ve canlı durum için Moonraker HTTP/WebSocket API’lerini kullanır. Klipper ve Moonraker gereklidir; Mainsail, Happy Hare ve Spoolman isteğe bağlı entegrasyonlar sunar.

Uygulama, Ender 3 V2’de kullanılan 4,3 inç paneli ve görsel kaynak düzenini hedefler. Diğer panel aileleri ve görsel paketleri birbirinin yerine kullanılamaz; [LCD uyumluluk notlarına](docs/lcd-assets.md) bakın.

## Özellikler

| İş akışı | v1.0.0 ile kullanılabilir |
|---|---|
| Baskı seçme ve başlatma | Alt klasörler, Mainsail sıralaması, JPEG önizleme, baskı metadatası ve Print/Cancel onayı |
| Hızlı önizleme | İlk beş görselin önceden yüklenmesi ve geçici LCD SRAM önbelleği |
| Baskı izleme | İlerleme, geçen/kalan süre, Pause/Resume, Stop ve Tune |
| Yazıcı ayarları | Homing, Move/Live Jog, ısıtıcı/fan hedefleri, çalışma zamanı Z offset ve hareket sınırları |
| Tabla kalibrasyonu | Dört köşe Screws Tilt Adjust, Bed Mesh Calibrate, kayıtlı Mesh Viewer ve Probe calibration |
| Entegrasyonlar | Düzenlenebilir Mainsail sıcaklık presetleri, Happy Hare kanal görünümü, Spoolman yüzdeleri ve M355 kabin ışığı |
| Sistem bilgileri | Kaydırılabilir host, yazılım ve MCU bilgileri; encoder ile güç açma/kapatma |

Menüler algılanan yazıcı yeteneklerine göre şekillenir. **MMU menüsü tam ekran Happy Hare kontrolü, canlı durum ve kurtarma sunar**; ana ekrandaki kanal görünümünün mevcut yerleşimi korunur. Diğer sınırlar [aşağıda](#kapsam-ve-sınırlar) listelenmiştir.

## Kurulum

### Donanım ve bağlantılar

UART/GPIO erişimi olan bir Linux SBC, Python 3.11 veya üzeri, uyumlu DWIN T5UIC1 panel ve çalışan Klipper/Moonraker kurulumu kullanın.

| Ekran bağlantısı | Raspberry Pi bağlantısı |
|---|---|
| RX | GPIO14 / UART TX |
| TX | GPIO15 / UART RX |
| Encoder A | GPIO21 |
| Encoder B | GPIO19 |
| Encoder düğmesi | GPIO20 |
| VCC | 5 V |
| GND | GND |

GPIO numaraları **BCM numaralandırmasını** kullanır. Encoder pinleri kurulum varsayılanlarıdır ve değiştirilebilir. Bağlantı örnekleri [images/](images/) dizinindedir.

`sudo raspi-config` ile seri donanımı etkinleştirin, seri giriş konsolunu kapatın ve yeniden başlatın. Pi modeliniz ve işletim sisteminiz için GPIO14/15’e yönlendirilen UART aygıtını doğrulayın; `/dev/ttyS0` kurulum varsayılanıdır, her sistemde aynı eşleşme geçerli değildir.

### Yükleme ve ayarlar

Standart repo konumundan çalıştırın:

```bash
cd ~
git clone https://github.com/sezgynus/KlipperDWIN.git
cd ~/KlipperDWIN
./install.sh
```

Kurulum bağımlılıkları yükler, `~/klipperdwin-env` ortamını oluşturur, bağlantı/pin ayarlarını sorar ve **`KlipperDWIN.service`** servisini etkinleştirir. Ayarlar repo dışında, `~/.config/KlipperDWIN/KlipperDWIN.env` dosyasında tutulur.

Ayrıca `moonraker.conf` yanına `KlipperDWIN.conf` oluşturur, include satırını ekler ve servisi Moonraker Update Manager’a kaydeder. Moonraker ayar dosyanız özel bir konumdaysa:

```bash
MOONRAKER_CONFIG=/path/to/moonraker.conf ./install.sh
```

Soruların varsayılanları: Moonraker `http://127.0.0.1:7125`, UART `/dev/ttyS0`, encoder pinleri `21 19`, düğme pini `20`, güç aygıtı `Printer` ve güç açma için `2000` ms basılı tutma. Enter ile varsayılanı kabul edebilirsiniz. Kurulumu tekrar çalıştırmak mevcut ayarları korur.

Ayarları sonradan değiştirmek için:

```bash
cd ~/KlipperDWIN
./configure.sh
```

Mevcut değerler varsayılan olarak gösterilir; kayıt sonrasında servis yeniden başlatılabilir. Kurulum servisi kurulum kullanıcısıyla çalıştırır ve mevcut `dialout`/`gpio` gruplarını ekler.

### Mainsail üzerinden güncelleme

Moonraker oluşturulan yapılandırmayı yükledikten sonra **Machine → Update Manager** bölümünde yenileyip **KlipperDWIN** bileşenini güncelleyin. Moonraker `master` dalını takip eder, gerektiğinde Python bağımlılıklarını günceller ve yönetilen servisi yeniden başlatır. Normal Update Manager güncellemesinde ayrıca bağımlılık yüklemeniz gerekmez.

> [!NOTE]
> Donanım ayarlarını harici yapılandırma dosyasında tutun. Takip edilen repo dosyalarındaki yerel değişiklikler Update Manager için gereken temiz çalışma ağacını bozar. Etiketler sürümleri belirtir; güncelleyici `v1.0.0` sonrasında da `master` dalını takip eder.

## Arayüz rehberi

Gezinmek için encoder’ı çevirin, seçmek için basın. Ekran etiketleri İngilizcedir; Türkçe README aynı menüleri açıklar.

### Ana ekran ve menü haritası

Ana ekranda sayfa başına dört ikon bulunur. Çevirmeye devam etmek sonraki veya önceki sayfaya geçirir; boş alanlar seçilmez. Logo/MMU paneli ve canlı durum alanı sabit kalır. Ana ekranın MMU veya Info menüsünden dönüşte seçili ikon korunur.

| Giriş | Açılan bölüm |
|---|---|
| Print | Dosya tarayıcısı → Print preview |
| Prepare | Move, Disable steppers, Home, Runtime Z offset, Screws Tilt Adjust, ön ısıtma ve soğutma |
| Control | Temperature, Motion, Probe calibration, jog kurtarma, Case Light ve Info |
| Leveling | Bed Mesh: Bed Mesh Calibrate ve Mesh Viewer |
| MMU | Tam ekran kanallar, filament işlemleri, bypass, canlı durum ve kurtarma |
| Info | Kaydırılabilir sistem bilgileri |

Bed mesh mevcutsa ilk sayfa **Print / Prepare / Control / Leveling**, ikinci sayfa **MMU / Info** olur. Bed mesh yoksa MMU dördüncü alanı alır, Info sonraki sayfada yer alır. İsteğe bağlı menü girişleri yalnızca destekleniyorsa görünür.

Durum alanı mevcut ısıtıcı sıcaklıklarını/hedeflerini, fanı, baskı hızı oranını, akış oranını, çalışma zamanı Z offset’i ve canlı XYZ konumlarını gösterir.

### Dosyalar ve sıralama

<p align="center"><img src="docs/assets/screens/print-file.png" width="260" alt="Dosya tarayıcısı"></p>

Tarayıcı geçerli klasörü **klasörler önce** olacak şekilde gösterir; boş klasörler dahil edilir ve yalnızca `.gcode` dosyaları listelenir (büyük/küçük harf duyarsız). `.thumbs` gibi noktayla başlayan dosya/klasörler gizlenir. Klasörü seçerek içine girin; **Back** üst klasöre, kök dizinde ise ana ekrana döner. Satırlarda yalnızca dosya adı görünse de baskı tam göreli yol üzerinden başlatılır.

Sıralama, Mainsail’in kayıtlı dosya adı, değiştirilme zamanı veya boyut kriterini ve artan/azalan yönünü izler; Moonraker’dan beş saniyede bir okunur. Her klasör seviyesinde aynı tercih uygulanır. Eksik, geçersiz veya desteklenmeyen tercihlerde **en yeni değiştirilen önce** sıralaması kullanılır. LCD bu tercihleri yalnızca okur. Mümkün olduğunda seçim dosya yolu üzerinden korunur; liste değişikliği sessizce başka bir dosya başlatamaz.

### Baskı önizlemesi

<p align="center"><img src="docs/assets/screens/print-preview.png" width="300" alt="Model ve kullanılan filamentlerle baskı önizlemesi"></p>

Dosyayı seçmek önizlemesini açar. **Başlangıçta Cancel seçilidir** ve aynı klasöre/dosyaya döner. **Print**, dosya sürümünü yeniden kontrol eder; baskı ekranını açmadan önce komut kabulünü ve yazıcı durum onayını bekler.

| Ekran etiketi | Moonraker metadatası |
|---|---|
| Print time | `estimated_time` |
| Tool changes | `filament_change_count` |
| Total usage | mm’den metreye çevrilen `filament_total` / gram olarak `filament_weight_total` |
| Filaments used | Kullanılan tool numarası, `filament_colors`, `filament_type` ve `filament_weights` |

Model sol üstte 128×128 alanda, özetler sağında; en fazla dört kullanılan tool altta gösterilir. Satırları `referenced_tools` belirler; yoksa pozitif tool ağırlıkları veya tek malzemeli metadata kullanılır. Tool numaraları slicer tool kimlikleridir; **fiziksel MMU kanal eşlemesi değildir**. Dörtten fazla tool kullanılırsa başlık gösterilen/toplam sayısını belirtir. Bilinmeyen değerler yer tutucuyla gösterilir; görsel olmaması metadata veya Print/Cancel kullanımını engellemez.

Görseller ve metadata Moonraker’dan alınır; uygulama G-code çözümlemez. JPEG görseller, flash’a yazmadan veya kurulu ikonları değiştirmeden geçici LCD SRAM’e aktarılır. Tarayıcı **geçerli sıralamadaki ilk beş dosyayı**, ilk dosyadan başlayarak önceden yükler. Değişmeyen kayıtlar klasör/sıralama değişiminde korunur; değiştirilen/silinen dosyalar ve yeniden bağlantılar eski kayıtları geçersiz kılar. Kalan alan diğer seçilen dosyaları LRU yöntemiyle önbellekler. Alan sınırı beş görselin tamamının sığmasını engelleyebilir; önceki dosyalar ön yüklemede önceliklidir, seçilen dosya gerektiğinde alan açabilir.

### Baskı ve Tune

<p align="center">
  <img src="docs/assets/screens/printing.png" width="240" alt="Baskı">
  <img src="docs/assets/screens/tune.png" width="240" alt="Tune">
</p>

Baskı ekranı dosya adı, ilerleme, geçen/kalan süre ve **Tune / Pause veya Resume / Stop** seçeneklerini gösterir. Tamamlanma, yuvarlanmış %100 değerine değil Klipper’ın `print_stats.state` durumuna bağlıdır. Duraklatma/devam/iptal işlemleri ilgili abonelik durumunu bekler.

Tune; baskı hızı, çalışma zamanı Z offset ve mevcut hotend/tabla/fan hedeflerini sunar. Açık editörün yerel hedefi onaylanana kadar korunur; canlı güncellemeler düzenlemeyi ezmez.

### Prepare, Move ve kalibrasyon

<p align="center">
  <img src="docs/assets/screens/prepare.png" width="240" alt="Prepare">
  <img src="docs/assets/screens/move.png" width="240" alt="Move ve Live Jog">
</p>

**Prepare → Move**, `gcode_move.position` üzerinden canlı komut koordinatlarını gösterir. Normal düzenleme onayla hedef gönderir; **Live Jog** encoder hareketini anında uygular. Hareket için homing gerekir, eksen sınırlarına uyulur ve baskı/duraklatma sırasında hareket reddedilir. Ekstrüzyon sıcaklık ve yapılandırılmış mesafe sınırlarını kontrol eder. Göreli jog G-code durumunu kaydeder/geri yükler; onaylanmamış geri yükleme yeni hareketi engeller ve **Control → Restore jog state** seçeneğini açar.

**Prepare → Screws Tilt Adjust → Calculate**, eksik eksenlere önce homing yaparak `SCREWS_TILT_CALCULATE` çalıştırır. Probe ve `[screws_tilt_adjust]` altında dört ayrı köşe vidası gerektirir.

<p align="center"><img src="docs/assets/screens/screws-tilt-success.png" width="280" alt="Screws Tilt Adjust sonucu"></p>

Köşeler yapılandırılmış XY konumlarına göre yerleşir; **Base** veya **CW/CCW** ve tur:dakika gösterilir. `01:20`, bir tam tur ve turun 20/60’ı demektir. Yön/miktarı Klipper verir; merkez talimatı en büyük gerekli ayarı seçer. Başarı için ölçülen en yüksek/en düşük nokta farkının **0,05 mm** altında olması gerekir; merkez mesajı yeşil olur. Ayar gerekiyorsa nötr beyaz kullanılır. **Continue**, yeniden ölçüm için Calculate menüsüne döner. Yapılandırma kaydı veya otomatik vida hareketi yapılmaz.

**Control → Probe calibration**, `PROBE_CALIBRATE`, açık `TESTZ` adımları, `ACCEPT` ve `ABORT` kullanır. Kayıt, ayrı ve korumalı bir `SAVE_CONFIG` işlemidir; Klipper’ı yeniden başlatır. Kalibrasyon işlemleri baskı, çakışan probe oturumu veya çözülmemiş hareket kurtarma sırasında engellenir; eski sonuçlar yeni başarı olarak gösterilmez.

### Bed Mesh ve kayıtlı profiller

**Home → Leveling**, **Bed Mesh** menüsünü açar. İlgili girişler Prepare veya Control altında tekrarlanmaz; burada toplanır.

| İşlem | Davranış |
|---|---|
| Bed Mesh Calibrate | Probe ile eksik eksenlere homing yapıp `BED_MESH_CALIBRATE` ile tam mesh ölçer |
| Ölçüm ekranı | Mevcut canlı probe değerlerini raw Z olarak bir ızgarada gösterir |
| Sonuç | Güncel `probed_matrix` yüksekliklerini, renkli daireleri ve min/max Z’yi gösterir |
| Continue | Menüye döner; ölçülen profil geçerli oturumda kalır |
| Save | Profil/yeniden başlatmayı onaylatır, bekleyen değişiklikleri kontrol edip `SAVE_CONFIG` ile kaydeder |
| Mesh Viewer | Current Mesh ve kayıtlı `bed_mesh.profiles` listesinden seçilen haritayı gösterir |

Viewer seçimi **profil yüklemez ve aktif mesh’i değiştirmez**. Haritada düşük Y alttadır. Save, oluşturulan `lcd_mesh_N` profilini kullanır ve yalnızca bekleyen değişiklikler tam olarak ölçülen profile aitse çalışır. İlgisiz bekleyen ayarlar kaydedilmez; yeniden başlatma yanıtının kaybolması kaydın tamamlandığını kanıtlamaz.

> [!IMPORTANT]
> Ölçüm sırasında **Cancel → Stop**, acil durdurma gönderir ve Klipper’ı shutdown durumuna geçirir. Onay ekranı bunu açıkça belirtir; devam etmek için `FIRMWARE_RESTART` kullanın. Save de yeniden başlatma gerektirir; Continue profili kalıcı kaydetmez.

### Control, sıcaklık ve çalışma zamanı hareket ayarları

<p align="center">
  <img src="docs/assets/screens/control.png" width="220" alt="Control">
  <img src="docs/assets/screens/temperature.png" width="220" alt="Temperature">
  <img src="docs/assets/screens/motion-runtime.png" width="220" alt="Çalışma zamanı Motion">
</p>

**Control → Temperature**, mevcut hotend/tabla/fan kontrollerini sunar. Mainsail preset adları ve etkin ısıtıcı hedefleri Moonraker veritabanından algılanır; Prepare ve Temperature menülerinde dinamik görünür. LCD’deki preset düzenlemeleri Mainsail’e geri kaydedilebilir. Uygulamak yazıcıyı ısıtır; yalnızca preset ayarlarını kaydetmek ısıtmaz. Fan ayarları sıcaklık presetleriyle senkronize edilmez. Mainsail presetleri yoksa harici yerel JSON deposu kullanılır; kullanılabilir olduğunda Mainsail esas alınır.

**Control → Motion**, `SET_VELOCITY_LIMIT` ile maksimum hız, maksimum ivme, square-corner velocity ve desteklenen minimum cruise ratio değerlerini düzenler. Bunlar **çalışma zamanı değerleridir**; otomatik olarak yapılandırmaya kaydedilmez.

### Info

<p align="center">
  <img src="docs/assets/screens/info-overview.png" width="220" alt="Sistem özeti">
  <img src="docs/assets/screens/info-software.png" width="220" alt="Yazılım sürümleri">
  <img src="docs/assets/screens/info-mcu-details.png" width="220" alt="MCU ayrıntıları">
</p>

**Home → Info** ve **Control → Info** aynı encoder ile kaydırılabilir özeti açar: makine boyutları, ağ/IPv4, host CPU yükü/sıcaklığı, kurulu yazılım sürümleri ve her bağlı MCU’nun durumu/yükü. MCU sıcaklığı eşleşen `temperature_mcu` kaynağı gerektirir; alınamayan değerler `N/A` gösterilir. KlipperDWIN, mevcutsa etiket sonrası commit’leri de içeren tam Update Manager Git sürümünü kullanır.

## İsteğe bağlı entegrasyonlar

### Happy Hare ve Spoolman

Happy Hare nesneleri mevcutsa ana ekranın logo alanı canlı kanal paneline dönüşür. Kanal/malzeme/renk/makara durumu için `mmu`, ünite adı için `mmu_machine`, çıkış LED renkleri için **`unitN_mmu_exit_leds`** kullanılır. Düşük parlaklıktaki renkler okunabilirlik için normalize edilir; tamamen kapalı LED’ler siyah kalır ve kanal numaraları kontrastlı siyah/beyaz metin kullanır.

Spoolman yüzdeleri tek bir aktif makaradan değil, Moonraker Spoolman proxy’si üzerinden her kanalın `gate_spool_id` değerinden alınır. Spoolman verisinin eksikliği diğer kanal bilgilerini devre dışı bırakmaz. **Ana ekran → MMU** ile ayrı tam ekran arayüzü açın. Genel hareket paneli MMU sayfalarında gizlenir; ana ekrana dönünce geri çizilir.

**Çevirerek odağı değiştirin; basarak açın veya kabul edin.** Sol üstteki Back oku seçilebilir. Uzun basış yapılandırılmış yazıcı güç davranışını korur. Kanallarda gezinmek ve detay açmak filament hareketi yaptırmaz.

| MMU sayfası | Kullanılabilir davranış |
|---|---|
| Home | Aktif kanalın sayfasında en fazla dört makara, seçili takım/kanal, filament yolu, nozzle sıcaklığı ve altı menü girişi |
| Gates / kanal detayları | Kaydırılabilir fiziksel kanal listesi; Select only, Load selected, eşlemeli Load/change, Unload, Eject spool, Preload ve Check |
| Filament / Assign spool | İsim, malzeme, renk, makara kimliği, kalan yüzde, sıcaklık ve mod; taslak kimlik atama veya ayrı atama silme |
| Tool map | Taslak takım–kanal düzenleyici; bas, çevir, bas ile kabul; Save/Cancel |
| EndlessSpool (Tool map içinden) | Taslak aç/kapat, gruplar ve kanal üyeliği; malzeme/renk uyumu, Save/Cancel |
| Bypass | Mevcut MMU kanalını boşaltma, bypass seçimi ve ardından yalnız ekstrüder yükleme/boşaltma |
| Manage / Recover | Kurtarma, manuel durum editörü, kilit açma/ısıtma ve Resume; bakım/seçenek girişleri |
| Maintenance / Options | Tüm kanalları kontrol, tek lineer selector için Home, desteklenen Grip/Release, yüklü filamentte gear sync ve sensör durumu |
| LEDs (Options içinden) | Aktif ünite için aç/kapat, animasyon ve çıkış modları; doğrulanan LED yapılandırması |
| Units (Options içinden) | Salt okunur ünite/kanal gezintisi; ünitenin ilk global kanalını ayrıca onayla seçme |
| Status | Gerçek işlem ve varsa Bowden aşama yüzdesi, ayrıştırılmış sensör durumları, gear sync, nozzle sıcaklığı ve işlem sonucu |

Ekrandaki **G1, Happy Hare tarafında `GATE=0`** anlamına gelir; takım numaraları T0'dan başlar. Birden fazla takıma eşlenen makara `T*` gösterir. Load selected mevcut dolu kanalı kullanır; Load/change ilişkili mantıksal takımı seçerek Happy Hare eşlemesini izler. Unload filamenti MMU'da park eder; Eject spool gerçek çıkarmayı açıkça ister ve gerektiğinde aktif kanalı önce boşaltır.

Her işlem hedefini belirten bir onay açar; **ilk odak Cancel üzerindedir**. Gönderim öncesinde durum yeniden kontrol edilir. Eksik, devre dışı, eski veya meşgul MMU verisi işlemleri kilitler. Baskı ve duraklama sırasında normal hareketler kapanır; kurtarmanın ayrı koşulları vardır. Devam eden işlem MMU arayüzü içinde kalır ve LCD'den kalibrasyon başlatılmasını engeller. Komutlar tamamlanması izlenen WebSocket RPC üzerinden gönderilir; ardından gerçek durum sorgulanır. Gönderim onayı fiziksel tamamlanma olarak gösterilmez. Başarısız veya doğrulanamayan sonuçlar kullanıcı onayıyla kapatılır; komutlar otomatik tekrarlanmaz.

Nedeni bildirilen bir MMU hata duraklaması Recover sayfasını doğrudan açar. Fiziksel sorunu düzeltin, otomatik kurtarma veya gerçek durumu bildirme işlemini yapın, gerekiyorsa kilidi açıp ısıtın ve Resume'u ayrıca seçin. Manuel Apply filament yükleyip boşaltmadan durumu bildirir; takım–kanal atamasını da düzeltebilir. Resume için baskının duraklamış, MMU'nun kilitsiz ve filamentin yüklü olması gerekir. Sensörlerde `CLEAR`, `TRIGGERED`, `UNKNOWN/OFF` ve `ABSENT` ayrı gösterilir; Bowden yüzdesi tüm takım değişimini değil ilgili aşamayı anlatır.

Tool map yalnızca baskı/duraklama dışında ve MMU boşta iken düzenlenir. Birden fazla takım aynı kanala eşlenebilir. Save değişen satırları onaylatır, tek `MMU_TTG_MAP MAP=...` komutu gönderir ve gerçek eşlemeyi doğrular; Cancel taslağı siler. Dışarıdan durum değişirse düzenleyiciyi yeniden açmak gerekir.

EndlessSpool aynı boşta ve baskı dışı koşulları kullanır. Enabled değerini bas, çevir, tekrar bas ile düzenleyin. Grubu açıp kanallara basarak üye ekleyin; çıkarılan üye ayrı gruba geçer (son üye korunur). Grup ekranında her kanalın malzeme/rengi ve aynı, karışık veya bilinmeyen veri durumu görünür; fiziksel makara uyumunu doğrulayın. Save tüm aç/kapat ve grup taslağını tek `MMU_ENDLESS_SPOOL ENABLE=... GROUPS=...` komutuyla gönderip iki alanı da doğrular. Üyelerden Back taslağı korur; EndlessSpool ekranındaki Cancel siler.

Filament → Assign spool ID ekranında pozitif sayısal kimliği bas, çevir, bas ile düzenleyip Save ve onayla kaydedin. Clear assignment ayrı onayla atamayı kaldırır; Cancel taslağı siler. Yerel atama yalnız bilinen `off`, `readonly` ve `push` modlarında açılır; `pull` ve bilinmeyen modlarda kilitlidir. Eksiksiz makara kimliği eşlemesi ve bilinen pozitif tam sayı filament sıcaklığı gerekir. Komut mevcut sıcaklığı korur; kimlik başka kanaldan taşınacaksa onayda gösterilir. Gerçek durum doğrulaması, önceki kanalın atamasının kaldırılması dahil tüm kimlik eşlemesini kontrol eder; makara kaydının varlığını veya asenkron Spoolman senkronizasyonunun tamamlandığını doğrulamaz.

Maintenance ve Options, doğrulanan Happy Hare v4 `mmu_machine` ünite bilgisini ve canlı selector durumunu okur. Desteklenmeyen kontroller gizlenir; eksik, meşgul, baskıda veya duraklamış durum işlemleri kilitler. Home yalnız tek ve bilinen lineer selector için açılır; sonrasında seçilecek takım onayda gösterilir. Grip/Release boş filament gerektirir; sürekli tutan ünitelerde Release gizlenir. Gear sync, bilinen aktif ünitede yüklü filament ister; sürekli tutan ünite senkronizasyondan çıkarılamaz. Lineer selector sürüş kontrolleri bilinen home durumu gerektirir. Her komutta Cancel odaklı onay ve canlı sonuç kontrolü vardır. Check all gates global kanal indekslerini kullanır; donanım bilgisi kalibrasyonun tamamlandığını kanıtlamaz. Kurulu komut davranışını gerçek donanımda doğrulayın.

Options ayrıca Cancel odaklı onayla MMU aç/kapat ve tüm MMU motorlarını bırakma sunar. İkisi de baskı/duraklama dışında boş filament gerektirir. Açma Happy Hare durumunu sıfırlar; kapalı MMU bu sayfadan açılabilir. Motor bırakma yalnız bilinen sürücü telemetrisi ve etkin MMU stepper yapılandırmasıyla görünür; `MMU_MOTORS_OFF UNIT=ALL` gönderilip yapılandırılmış tüm MMU sürücülerinin ve gear sync durumunun kapalı olduğu kontrol edilir. Home bilgisi kaybolabilir. Sürücü bayrakları servo enerjisini veya fiziksel hareketi kanıtlamaz.

Options → LEDs yalnız doğrulanmış aktif ünite `mmu_leds <isim>` telemetrisiyle görünür. Aç/kapat, animasyon ve çıkış modları (`off`, `gate_status`, `filament_color`, `slicer_color`) üniteye özel `MMU_LED UNIT=...` komutuyla gönderilip gerçek LED nesnesi sorgulanır. Raporlanan yapılandırma fiziksel LED çıktısını kanıtlamaz. Desteklenmeyen veya bilinmeyen durum kontrolleri kilitler; özel efektler ve entry/status/logo düzenleme web arayüzünde kalır.

Options → Units yalnız doğrulanmış çoklu ünite kanal dağılımında görünür. Ünitelerde ve kanallarda gezinmek komut göndermez; kanal numaraları global kalır. Select this unit ünitenin ilk kanalı için `MMU_SELECT GATE=...` onayı açar; selector home veya hareket yapabilir ve baskı/duraklama dışında boş filament gerektirir. Sonuçta sorgulanan aktif ünite ve kanal birlikte doğrulanır. Tek üniteli kurulumlarda bu tarayıcı gösterilmez.

Bu kontrol uygulaması [MMU tasarımını](https://github.com/sezgynus/KlipperDWIN/tree/docs/mmu-menu-demo/docs/mmu-menu-demo) esas alır. Kalibrasyon ve ileri LED yapılandırması için web arayüzünü kullanın. Gerçek komut davranışı kurulu Happy Hare sürümüne ve yapılandırmasına bağlıdır; eksik telemetri ilgili işlemi kilitli bırakır.


### Case Light

<p align="center"><img src="docs/assets/screens/case-light.png" width="240" alt="Case Light"></p>

**Control → Case Light**, `gcode_macro M355` mevcutsa görünür. Aç/kapat ve %0–100 parlaklık sunar; parlaklık 0–255 macro değerine çevrilir. Çift yönlü durum için macro aşağıdaki komutları kabul etmeli ve sorgu formatını döndürmelidir:

```text
M355 S0/1
M355 P0..255

Light is ON, Brightness=128
```

### Encoder ile güç kontrolü

Encoder düğmesini basılı tutarak Moonraker güç aygıtı açılabilir; Klipper veya LCD UART çevrimdışı olsa da çalışır. Aygıt adı ve basılı tutma süresini `./configure.sh` ile ayarlayın. Varsayılanlar `Printer` ve **2 saniye**; `0` ms, basıldığında hemen güç açma ister.

Her menünün sağ üstünde aynı güç ikonu bulunur. İlk menü öğesindeyken encoderi saat yönünün tersine çevirerek ikona odaklanın; saat yönünde çevirerek menüye dönün. Odaklanmış ikonda encoder düğmesine basmak **Turn off printer?** onay penceresini açar ve **Yes varsayılan seçilidir**. Yes onaylandığında yalnızca yapılandırılmış Moonraker güç aygıtının bildirilen durumu `on` ise kapatma komutu gönderilir; No, gelinen menüye döner.

## Yapılandırma

Kurulan servisler `~/.config/KlipperDWIN/KlipperDWIN.env` dosyasını okur. Bu bir systemd EnvironmentFile dosyasıdır, shell betiği değildir. `MOONRAKER_API_KEY` ve istek zaman aşımı burada düzenlenebilir; etkileşimli ayarlayıcı bunları korur. CLI argümanları ortam değerlerinden önceliklidir.

| Ortam değişkeni | CLI argümanı | Kurulum ayarı | Yalın `run.py` varsayılanı |
|---|---|---|---|
| `MOONRAKER_URL` | `--moonraker-url` | `http://127.0.0.1:7125` | Aynı |
| `MOONRAKER_API_KEY` | Yalnızca ortam | Boş | Boş |
| `DWIN_REQUEST_TIMEOUT` | `--request-timeout` | 5 saniye | 5 saniye |
| `DWIN_SERIAL_PORT` | `--serial-port` | `/dev/ttyS0` | `/dev/ttyAMA0` |
| `DWIN_ENCODER_PINS` | `--encoder-pins A B` | `21 19` | `21 19` |
| `DWIN_BUTTON_PIN` | `--button-pin` | `20` | `13` |
| `DWIN_SETTINGS_FILE` | `--settings-file` | `~/.config/KlipperDWIN/presets.json` | `$XDG_CONFIG_HOME/dwin-lcd/presets.json` veya `~/.config/dwin-lcd/presets.json` |
| `DWIN_POWER_DEVICE` | `--power-device` | `Printer` | `Printer` |
| `DWIN_POWER_ON_HOLD_MS` | `--power-on-hold-ms` | `2000` | `2000` |

Yalın varsayılanlar, ortam dosyası veya CLI değeri verilmediğinde geçerlidir. Manuel hata ayıklamada UART/GPIO’nun tek sahibi olması için önce servisi durdurun. Bu örnek kurulumun pinlerini/aygıtını açıkça belirtir:

```bash
sudo systemctl stop KlipperDWIN.service
cd ~/KlipperDWIN
~/klipperdwin-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 19 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

Manuel süreçten çıktıktan sonra `sudo systemctl start KlipperDWIN.service` ile servisi tekrar başlatın. Manuel bağımlılık güncellemesi için `~/klipperdwin-env/bin/python -m pip install -r requirements.txt` kullanın; normal Mainsail güncellemeleri bunu otomatik yapar.

## Sorun giderme

```bash
sudo systemctl status KlipperDWIN.service --no-pager
journalctl -u KlipperDWIN.service --since "10 minutes ago" --no-pager
sudo systemctl restart KlipperDWIN.service
```

| Belirti | Kontrol |
|---|---|
| Ekran yok / UART yeniden bağlanıyor | Güç, çapraz TX/RX, seçilen UART, seri konsol ve aygıt izinleri |
| Encoder yanıt vermiyor | BCM pin ayarları, bağlantılar ve gpiochip izinleri |
| İsteğe bağlı menü eksik | Eşleşen Klipper nesnesi/yapılandırması ve geçerli Moonraker bağlantısı |
| Önizleme verisi eksik | Moonraker dosya metadatası, slicer alanları ve thumbnail varlığı |
| Önizleme yavaş geliyor | `Thumbnail` indirme/dönüştürme/aktarım/önbellek logları; arka plan süresi tarayıcı dışında geçirilen zamanı içerebilir |
| Yerel değişiklikler güncellemeyi engelliyor | Çalışma ayarlarını takip edilen dosyaların dışında tutun; repo değişikliklerini inceleyin |
| İşlem başarısız veya yanıt kayboldu | Tekrarlamadan önce gerçek yazıcı durumunu inceleyin |

İletişim ve işlem hataları loglanır; ancak temiz log fiziksel hareketi, ekran görünümünü veya kalıcı kaydı kanıtlamaz. Görsel sorunlarda ekran fotoğrafı ekleyin.

## Kapsam ve sınırlar

- Arayüz uyumlu 272×480 DWIN T5UIC1 kaynaklarını hedefler; diğer ekran aileleri ayrıca doğrulanmalıdır.
- MMU kalibrasyonu ve ileri LED efektleri web arayüzünde kalır. Çoklu ünite Home için ünite başına canlı home telemetrisi gerekir; bu işlem sunulmaz. Kanallar Happy Hare global indekslerini kullanır; mevcut ana ekran kanal/LED yerleşimi korunur.
- Önizleme en fazla dört kullanılan tool gösterir; tool başına uzunluk, marka adı ve fiziksel kanal eşlemesi gösterilmez.
- SRAM önbelleği geçicidir ve 32 KiB ile sınırlıdır; yeniden bağlantı/başlatma sonrası yeniden kurulur.
- Screws Tilt dört ayrı köşe gerektirir; sabit 0,05 mm en yüksek/en düşük nokta farkı başarı eşiği kullanır.
- Mesh haritaları en fazla 25×25 nokta destekler. Yoğun haritalarda bazı etiketler atlanır; her nokta çizilir ve min/max hesabına dahil edilir.
- Canlı mesh ilerlemesi standart probe konsol yanıtlarına bağlıdır. Bunları vermeyen yöntemlerde de son sonuç gösterilebilir.
- Mesh iptali Klipper’ı shutdown durumuna geçirir; kalıcı kalibrasyon kayıtları Klipper’ı yeniden başlatır.
- Çalışma zamanı hareket ve Z-offset düzenlemeleri, kalıcı probe/yapılandırma kalibrasyonundan ayrıdır.
- Daha geniş panel, bağlantı ve yazıcı uyumluluğu fiziksel test gerektirir.

## Geliştirme

### Mimari ve komut yönetimi

Tek UI sahibi thread; çizim, gezinme ve UART yazımlarını yönetir. GPIO callback’leri girdi olaylarını kuyruğa ekler. Moonraker WebSocket abonelikleri birleştirilmiş değiştirilemez durum sağlar; sıralı HTTP worker komutları işler, uzun tabla kalibrasyonları tamamlanması izlenen WebSocket RPC kullanır.

Yanıt tabanlı panel heartbeat'i, Linux UART aygıtı açık kalmış olsa bile LCD güç çevrimini algılar. Yeniden bağlantıda ekran ve geçici atlas/cache durumu persistent Picture Flash'tan geri yüklenir; değişmemiş atlas verisi Flash'a yeniden yazılmaz.

Bağlantı epoch’ları eski girdileri ve kuyruktaki komutları reddeder. Başarısız yazıcı komutları **otomatik tekrar gönderilmez**. Yeniden bağlantı arayüzü çizer ve geçici önbellekleri yeniden kurar. Zaman aşımı, komutun yazıcıya ulaşıp yanıtın kaybolduğu anlamına gelebilir; tekrarlamadan önce gerçek durumu inceleyin.

| Modüller | Sorumluluk |
|---|---|
| `dwinlcd.py`, `ui_*.py` | Gezinme, özellik ekranları ve UI olay sahipliği |
| `printerInterface.py`, `printer_state.py`, `printer_capabilities.py` | Yazıcı işlemleri, normalize durum ve mevcut kontroller |
| `moonraker_client.py`, `moonraker_subscription.py`, `command_feedback.py` | HTTP/WebSocket iletişimi ve komut onayı |
| `screws_tilt.py`, `bed_mesh.py`, `probe_wizard.py` | Kalibrasyon durum makineleri ve sonuç/yapılandırma korumaları |
| `thumbnail_preview.py`, `thumbnail_cache.py`, `preview_metadata.py` | JPEG hazırlığı, SRAM alan yönetimi ve isteğe bağlı metadata |
| `t5uic1_driver.py`, `encoder.py`, `ui_events.py` | Tam T5UIC1 protokol sürücüsü, GPIO girdileri ve olay döngüsü |
| `preset_store.py`, `motion_settings.py`, `system_info.py` | Preset kaydı, çalışma zamanı sınırları ve sistem telemetrisi |

Hareket ve kalibrasyon komutları gönderilirken canlı baskı, home ve oturum durumu yeniden kontrol edilir; eski jog konumu reddedilir. Hareket hatasından sonra MOVE=0 temizliğinin çalışabilmesi için jog geri yükleme ayrı bağlantı kontrolü kullanır.

SAVE_CONFIG gönderiminde onaylanan pending ayarların tam kümesi ve değerleri yeniden doğrulanır; mesh kaydında ölçülen current/profile verisi de kontrol edilir. Diğer istemcilerden gözlenen değişiklikler kaydı geçersiz kılar. Bu istemci kontrolü tüm Moonraker istemcilerini kapsayan atomik kilit değildir.

Preset, dosya listesi, klasör, sıralama ve Info HTTP okumaları sınırlı bir arka plan kuyruğunda çalışır; beklerken arayüz kullanılabilir. Baskı onayı dosyayı asenkron doğrular; İptal veya bağlantı değişimi bekleyen doğrulamanın baskı başlatmasını engeller. Mainsail preset yazımları da asenkron tamamlanır ve hatalar ekranda gösterilir.

Komut geri bildirimi, taşıma Future sonucu gelmese de süre sınırına tabidir. Süresi dolan işlem geç gelen sonuçla başarılı sayılmaz; tekrar denemeden önce yazıcı durumunu kontrol edin.

MMU kontrolleri, isteğe bağlı ana ekran RGB verisinden bağımsız olarak doğrulanmış canlı kontrol durumunu kullanır. Eksik veya bozuk gate renkleri ana ekran şeridini gizleyebilir; geçerli menü işlemlerini kapatmaz. Baskı, meşguliyet, fiziksel durum ve gönderim kontrolleri uygulanmaya devam eder.

HTTP JSON yanıtları, dosya listesi, metadata ve komut sonuçları dahil varsayılan olarak 8 MiB ile sınırlıdır. Entegrasyonlar `MoonrakerClient(max_json_bytes=...)` ile pozitif tamsayı byte sınırı belirleyebilir. Okuyucu Content-Length bilgisinden bağımsız sınır uygular; büyük yanıtlar hata verir ve komutlar otomatik tekrarlanmaz.

T5UIC1 LCD'nin donanım yapılandırması, firmware/görsel kaynakları, bellek düzeni ve çalışma zamanı protokolü [`docs/t5uic1-reference.md`](docs/t5uic1-reference.md) içinde birlikte belgelenmiştir.

MMU tam ekran sayfaları tam T5UIC1 sürücüsünü kullanır; başlığın sağ üstü yönetilen güç ikonuna ayrılmıştır. MMU Back seçiliyken bir adım daha saat yönünün tersine dönüş güç ikonuna odaklanır; saat yönünde dönüş Back’e döner. Güç popup’ında No seçmek, taslak ve seçim dahil MMU sayfasını tamamen geri çizer. Özel statik ikonlar master atlas tablosunu kullanır; MMU canlı gate/filament grafikleri dinamik kalır. Panel kaybı veya bağlantı dönemi değişimi açık MMU güç popup’ını kapatma komutu göndermeden iptal eder. Ayrıntılar [sürücü entegrasyon kaydında](docs/mmu-driver-integration.md).

### Regresyon testleri

```bash
cd ~/KlipperDWIN
~/klipperdwin-env/bin/python -m unittest discover -s tests -v
```

Testler gerçek UI/backend metotlarını izole durum ve taklit seri/GPIO/ağ I/O ile çalıştırır. Kapsam; menü sayfaları, klasörler/sıralama, önizleme metadatası/önbellek geçersizleştirme, UART paketleri/kurtarma, komut epoch’ları, hareket korumaları, presetler ve kalibrasyon kayıt/iptal akışlarını içerir. Fiziksel yazıcı/panel testinin yerini almaz. [Test sözleşmeleri](tests/README.md), [LCD kaynak envanteri](docs/lcd-assets.md) ve [geçmiş kaynak audit’i](docs/source-audit.md) ek bilgi sağlar.

### Katkıda bulunma

Issue ve pull request’ler kabul edilir. Davranış değişikliklerine ilgili regresyon kapsamını ekleyin. Hata bildirimlerinde Pi/işletim sistemi, UART aygıtı, encoder BCM pinleri, yazılım sürümleri, isteğe bağlı bileşenler, loglar ve görsel sorunlarda fotoğraf paylaşın.

## Katkılar ve lisans

Proje [odwdinc/DWIN_T5UIC1_LCD](https://github.com/odwdinc/DWIN_T5UIC1_LCD) ve [bustedlogic/DWIN_T5UIC1_LCD](https://github.com/bustedlogic/DWIN_T5UIC1_LCD) çalışmalarından doğmuştur. Özgün telif bildirimleri ve Git geçmişi korunur.

Entegrasyonlar [Klipper](https://github.com/Klipper3d/klipper), [Moonraker](https://github.com/Arksine/moonraker), [Mainsail](https://github.com/mainsail-crew/mainsail), [Happy Hare](https://github.com/moggieuk/Happy-Hare) ve [Spoolman](https://github.com/Donkie/Spoolman) kullanır.

**GNU GPL v3.0** lisanslıdır. [LICENSE](LICENSE) dosyasına bakın.
