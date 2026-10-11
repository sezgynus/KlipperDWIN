# Günlük kullanım

[English](user-guide.md) · [Türkçe](user-guide_TR.md) · [Dokümantasyon](README_TR.md)

## Gezinme ve durum alanı

Seçimi taşımak için çevirin; seçmek için basın. Sayısal değere basın, düzenlemek için çevirin ve uygulamak için tekrar basın. **Back** önceki ekrana döner. Ana ekran her sayfada dört ikon gösterir; sayfa değiştirmek için çevirmeye devam edin. Noktalar aktif sayfayı belirtir. İsteğe bağlı öğeler yazıcınızın yapılandırmasına bağlıdır.

Sabit durum alanı sıcaklık/hedefleri, fanı, hız/akış bilgisini, çalışma zamanı Z offset'i ve XYZ koordinatlarını gösterir. Hız ve ekstrüzyon alanları override yüzdeleri ile gerçek hız/hacimsel akış arasında dönüşümlü gösterilir. MMU sayfaları kendi durum düzenini kullanır.

## Baskı seçme ve başlatma

<p align="center">
  <img src="assets/screens/print-file.png" width="240" alt="Dosya tarayıcısı">
  <img src="assets/screens/print-preview.png" width="240" alt="Model ve filament önizlemesi">
</p>

1. **Home → Print** açın. Klasör veya G-code dosyası seçin. Klasörler önce gelir; **Back** bir üst klasöre, kök klasörde ise ana ekrana döner.
2. Slicer sağlıyorsa model önizlemesini, tahmini süreyi, takım değişimlerini, toplam filament uzunluğu/ağırlığını ve kullanılan filament renklerini/malzemelerini/ağırlıklarını kontrol edin.
3. Başlatmak için **Print** seçip basın veya aynı dosyaya dönmek için **Cancel** seçin. Başlangıçta Cancel seçilidir.

Tarayıcı Mainsail'in ad/tarih/boyut sıralamasını ve yönünü izler. Geçerli tercih yoksa en yeni dosyalar önce gelir. Gizli klasörler ve G-code dışındaki dosyalar gösterilmez.

Eksik thumbnail veya metadata baskıyı engellemez. En fazla dört kullanılan takım gösterilir; T0 gibi takım ID'leri slicer takımlarıdır, fiziksel MMU kanal numarası değildir. Sık açılan önizlemeler gezinmeyi hızlandırmak için önceden hazırlanır.

## Baskı ve Tune

<p align="center">
  <img src="assets/screens/printing.png" width="240" alt="Baskı ilerlemesi ve kontroller">
  <img src="assets/screens/tune.png" width="240" alt="Tune">
</p>

Baskı ekranı dosyayı, ilerlemeyi ve geçen/kalan süreyi gösterir. Gerektiğinde **Pause**, **Resume** veya **Stop** kullanın. Baskı hızını, mevcut hotend/tabla/fan ayarlarını veya çalışma zamanı Z offset'i değiştirmek için **Tune** açın. Akış durum alanında gösterilir; LCD'de akış düzenleyicisi yoktur.

Çalışma zamanı Z offset mevcut oturumu ayarlar. Kalıcı probe offset kaydetmez. İşlem başarısızsa veya sonucu belirsizse tekrarlamadan önce Mainsail'den kontrol edin.

## Prepare ve Live jog

<p align="center">
  <img src="assets/screens/prepare.png" width="240" alt="Prepare menüsü">
  <img src="assets/screens/move.png" width="240" alt="Move, Live jog kapalı">
  <img src="assets/screens/move-live-jog.png" width="240" alt="Move, Live jog açık">
</p>

**Prepare → Home** yazıcıyı home eder. **Disable steppers** motorları bırakır. **Runtime Z offset** mevcut oturumun offset'ini değiştirir.

**Prepare → Move** içinde X, Y, Z veya Extruder seçin, değeri düzenleyin ve uygulamak için basın. **Live jog [X]** açıkken encoder ile düzenleme anında hareket ettirir; **[ ]** durumunda hareket onaylandığında uygulanır.

Önce gerekli eksenleri home edin. Baskı ve duraklama sırasında hareket kullanılamaz; hareket sınırları uygulanır. Ekstrüzyondan önce nozulu ısıtın. Başarısız jog sonrası hareket kilitli kalırsa yazıcıyı kontrol edin ve sunulduğunda **Control → Restore jog state** kullanın.

## Sıcaklık ve ön ısıtma presetleri

<p align="center">
  <img src="assets/screens/temperature.png" width="240" alt="Sıcaklık kontrolleri">
  <img src="assets/screens/prepare-preheat.png" width="240" alt="Prepare içinde adlandırılmış ön ısıtma presetleri">
</p>

- **Prepare → Preheat [ad]** preset'i uygular. **Cooldown** ısıtıcıları kapatır.
- **Control → Temperature** mevcut hotend, tabla ve fan hedeflerini değiştirir.
- Preset'in **[ad] settings** bölümünü açın, ısıtıcı hedeflerini düzenleyin ve **Save settings** seçin. Preset kaydetmek ısıtmayı başlatmaz.

Mevcutsa preset adları ve ısıtıcı hedefleri Mainsail ile paylaşılır; LCD düzenlemeleri oraya kaydedilir. Mainsail presetleri yoksa yerel presetler kullanılır. Fan ayarları sıcaklık presetleriyle eşitlenmez.

## Çalışma zamanı hareket sınırları

<p align="center">
  <img src="assets/screens/control.png" width="240" alt="Control menüsü">
  <img src="assets/screens/motion-runtime.png" width="240" alt="Çalışma zamanı hareket sınırları">
</p>

Maksimum hız, maksimum ivme, square-corner velocity ve destekleniyorsa minimum cruise ratio için **Control → Motion** açın. Alana basın, çevirin ve uygulamak için basın. Değişiklikler çalışma zamanı ayarlarıdır; kalıcı varsayılan istiyorsanız Klipper yapılandırmasını ayrıca düzenleyin.

## Vida ayarı

Klipper'ın `[screws_tilt_adjust]` yapılandırmasında probe ve dört ayrı köşe vidası gerektirir.

<p align="center">
  <img src="assets/screens/screws-tilt.png" width="220" alt="Vida ayarını hesaplama">
  <img src="assets/screens/screws-tilt-probing.png" width="220" alt="Köşeler ölçülüyor">
  <img src="assets/screens/screws-tilt-reading-results.png" width="220" alt="Sonuçlar okunuyor">
  <img src="assets/screens/screws-tilt-success.png" width="220" alt="Köşeler düzeltildi">
</p>

1. **Leveling → Screws Tilt Adjust → Calculate** açın. Eksik eksenler ölçümden önce home edilir.
2. **Probing corners…** ve **Reading results…** aşamalarını bekleyin.
3. **Base** vidasını değiştirmeyin. Diğer vidaları **CW** (saat yönü) veya **CCW** (saat yönünün tersi) ve gösterilen miktara göre çevirin. `01:20` bir tam tur ve turun 20/60'ı demektir.
4. **Continue** seçin, gerektiğinde ayarlayın ve tekrar hesaplatın. Yeşil **Corners leveled / Tolerance achieved!**, ölçülen en yüksek/en düşük farkın **0,05 mm** altında olduğunu belirtir.

Vidaları siz ayarlarsınız; ekran ölçüm ve yönlendirme yapar. Bu işlem yapılandırma kaydetmez.

## Bed mesh ve kayıtlı profiller

<p align="center">
  <img src="assets/screens/bed-mesh.png" width="240" alt="Bed Mesh menüsü">
  <img src="assets/screens/mesh-viewer.png" width="240" alt="Kayıtlı mesh profilleri">
  <img src="assets/screens/mesh-pei.png" width="240" alt="Mesh yükseklik haritası">
</p>

**Home → Leveling → Bed Mesh** açın. Probe yapılandırılmışsa **Calibrate** eksik eksenleri home edip tablayı ölçer. Ölçüm sonrası renkli yükseklik haritasını ve minimum/maksimum Z değerlerini inceleyin.

- **Continue** menüye döner ve ölçülen mesh'i mevcut oturum için korur.
- **Save** profil ve yeniden başlatma onayı ister. Ölçülen mesh oluşturulan `lcd_mesh_N` profiline kaydedilir; Klipper yeniden başlar. İlgisiz bekleyen yapılandırma değişiklikleri kaydı engelleyebilir.
- **Mesh Viewer**, Current Mesh veya kayıtlı profilleri incelemenizi sağlar. Görüntülemek profil yüklemez, yazıcıyı hareket ettirmez ve aktif mesh'i değiştirmez. Düşük Y haritanın altındadır.

**Ölçüm sırasında Cancel → Stop acil durdurmadır:** Klipper shutdown durumuna girer. Kurtarmak için web konsolundan `FIRMWARE_RESTART` kullanın. Ölçümün sürmesini istiyorsanız onayı iptal edin.

## Probe offset kalibrasyonu

1. XYZ home edin ve **Prepare → Move** ile nozulu uygun kalibrasyon XY noktasına götürün.
2. **Leveling → Probe Calibration → Start** açın.
3. Alt ve üst denenmiş konumların arasında canlı Z yüksekliğini izleyin. Düğmeyi çevirerek dört **-- / - / + / ++** butonundan birini seçin ve basarak Klipper'ın arama adımlarıyla hareket edin.
4. Uygunsa **Accept**, oturumu iptal etmek için **Cancel** seçin.
5. Accept sonrası kalıcı kayıt ve Klipper'ı yeniden başlatmak için **Save**, kaydetmeden çıkmak için **Continue** seçin.

Baskı durmuş olmalıdır. Bekleyen yapılandırma değişiklikleri kalibrasyonu engellemez. Kayıt yalnızca bekleyen değişiklik kabul edilen prob ofsetinden oluşuyorsa yapılabilir. Kayıt Klipper'ı yeniden başlatır; geçici çalışma Z ofsetinden ayrıdır.

## Ekran ayarları

<p align="center"><img src="assets/screens/display.png" width="240" alt="Parlaklık ve boşta kısma"></p>

**Home → Display** açın:

| Ayar | Kullanım |
|---|---|
| Brightness | Normal parlaklık, %0–100; değişiklik düzenleme sırasında görünür |
| Idle dim | Off veya encoder girdisi olmadan 1–60 dakika sonra kısma |
| Dim brightness | Kısılmış parlaklık, %0–100; normal parlaklıkla sınırlanır |

Düzenlemek için basın, çevirin ve kaydetmek için tekrar basın. Ayarlar ekranın güç döngüsünde korunur. Varsayılanlar **%100**, **Off** ve **%10**'dur. Kayıt başarısızsa düzenleme açık kalır; yeniden denemek için basın.

Boşta kısma sonrası ilk encoder hareketi veya tıklama, menü işlemi yapmadan ekranı uyandırır. **%0 arka ışığı kapatır**; Brightness düzenlerken saat yönünde çevirerek tekrar artırın.

## Bakım

**Home → Maintenance**, Info’dan önceki menüdür. Şimdilik yalnızca **Back** seçeneğini içerir; bu seçenek ana menüde aynı ikona döner.

## Info ve güncellemeler

<p align="center">
  <img src="assets/screens/info-overview.png" width="220" alt="Makine, Wi-Fi ve host">
  <img src="assets/screens/info-mcu-details.png" width="220" alt="MCU durumu">
  <img src="assets/screens/info-mcu-overview.png" width="220" alt="MCU ve yazılım bölümleri">
  <img src="assets/screens/info-software.png" width="220" alt="Yazılım sürümleri">
</p>

**Home → Info** veya **Control → Info** açın; Machine, Host, MCUs ve Software bölümlerini kaydırmak için çevirin. Yazıcı boyutlarını, ağ/IP'yi, Wi-Fi adını/sinyalini, CPU/RAM/sıcaklığı, MCU bağlantısını/yükünü/sıcaklığını ve kurulu yazılım sürümlerini kontrol edin. Bulunamayan değerlerde `N/A` veya kullanılamıyor durumu gösterilir. MCU sıcaklığı yapılandırılmış `temperature_mcu` kaynağı, Wi-Fi ayrıntıları Linux `iw` gerektirir.

<p align="center">
  <img src="assets/screens/info-project.png" width="220" alt="Proje QR ve güncelleme kontrolü">
  <img src="assets/screens/info-update-checking.png" width="220" alt="Güncelleme kontrol ediliyor">
  <img src="assets/screens/info-update-current.png" width="220" alt="Güncel">
</p>

Repoyu açmak için proje QR kodunu tarayın. LCD'den güncellemek için:

1. Yazıcıyı boşta bırakın ve **Check for updates** düğmesine kaydırın. Encodere basın.
2. **Checking…** aşamasını bekleyin. Yeşil **Up to date** güncelleme gerekmediğini gösterir; güncelleme varsa düğme **Update** olur.
3. KlipperDWIN'i yüklemek için **Update** seçin. Moonraker ardından servisi yeniden başlatır. Bu işlem tüm yazıcı bileşenlerini güncellemez.

Repo kirli veya geçersizse **Soft recovery**, ikinci bir **Confirm recovery** adımı sunar. Kurtarma yerel repo değişikliklerini siler; gerekenleri önceden yedekleyin. Çevirmek onayı iptal eder. Kurtarma otomatik güncelleme yüklemez. Sonuç doğrulanmamışsa tekrar denemeden önce Mainsail Update Manager'dan kontrol edin.

## Kabin ışığı

<p align="center"><img src="assets/screens/case-light.png" width="240" alt="Case Light"></p>

**Control → Case Light**, yapılandırılmış `output_pin case_light` için görünür. On/Off kullanın ve PWM parlaklığı %0–100 ayarlayın. On son pozitif parlaklığı, bilinmiyorsa %100'ü geri getirir. Makro gerekmez.

PWM destekli çıkış aşağıdaki gibi ayarlanabilir; `PA3` yerine gerçek ışık kontrol pininizi yazın:

```ini
[output_pin case_light]
pin: PA3
pwm: True
value: 1.0
shutdown_value: 0
cycle_time: 0.01
```

## Yazıcı gücü

Moonraker güç aygıtı adını `./configure.sh` ile ayarlayın. Açmak için encoder düğmesini basılı tutun; varsayılan süre **2 saniye**. Pi/servis ve Moonraker erişilebilir kaldığı sürece Klipper veya ekran çevrimdışıyken de çalışır.

Kapatmak için ilk menü öğesinden (MMU sayfalarında Back) saat yönünün tersine çevirerek sağ üst güç ikonuna odaklanın. **Turn off printer?** açmak için basın; **başlangıçta Yes seçilidir**. Yapılandırılmış aygıtı kapatmak için Yes onaylayın veya dönmek için No seçin.

Pi çalışmaya devam ederken röle yazıcı ve ekranı birlikte besliyorsa, yeniden güç açıldığında ilk ana ekran sayfasına dönülür. Menüleri kullanmadan önce açılışın bitmesini bekleyin.
