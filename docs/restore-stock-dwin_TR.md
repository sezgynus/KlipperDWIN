# Orijinal DWIN ekran kaynaklarına dönüş

[English](restore-stock-dwin.md) · [Türkçe](restore-stock-dwin_TR.md) · [LCD uyumluluğu](lcd-assets_TR.md)

> **Uyarı — bu işlem LCD'nin kalıcı firmware/kaynak belleğine yazar.** Bu rehberi yalnızca orijinal Ender-3 V2 **DWIN T5UIC1** ekranında kullanın. `DWIN_SET` dosyaları **DACAI, TJC veya başka ekran kontrolcüleriyle uyumlu değildir**. Ekrana müdahale etmeden önce enerjiyi kesin.

## Neler geri yüklenir?

Petrel'in yeni sürümleri, özel açılış JPEG'ini Picture Flash **0** yuvasına; oluşturduğu ikon kütüphanesi **3**'ü Picture Flash **3–15** yuvalarına yazar (yalnızca mevcut paket için gerekli bloklar yazılır). Stok ikonlar Petrel'in ihtiyaç duyduğu simgeleri, seçim durumlarını, animasyonları ve arayüz bileşenlerini karşılamadığından bu yöntem görsel tutarlılığı ve çizim performansını artırır. Değişen Flash blokları UART üzerinden yüklenir; ayrı Data Flash'taki parmak izleri gereksiz tekrarları önler. Baskı küçük resimleri geçici SRAM kullanır ve kalıcı kaynakları değiştirmez. Petrel'in ASCII fontu ayrıca SD karttan kurulur; Petrel LCD kernel firmware'ini veya fontu kendiliğinden yeniden yazmaz.

**Orijinal Creality Ender-3 V2 DWIN_SET** paketi [`assets/stock-dwin/DWIN_SET`](../assets/stock-dwin/DWIN_SET) konumundadır. OEM açılış görselini, İngilizce/Çince sayfaları, ikon kütüphanesi **9**'u, T5UIC1 yapılandırmasını ve LCD kernel dosyasını içerir. Kaynak: [Creality GPL-3.0 deposu](https://github.com/CrealityOfficial/Ender-3V2/tree/88a603b396d09607f4b25bf1bd1c5881092380c0/UI/DWIN_SET). Ayrıntılar için [paket kaydı](../assets/stock-dwin/README_TR.md).

**Sınırlar:** Bu paket stok ekran yazılımının kullandığı OEM kaynaklarını geri yükler; Picture Flash'ta daha önce yazılmış bütün yuvaları bayt bayt silmeyi garanti etmez. Creality'nin bu kaynak paketinde orijinal `0T5UIC1.HZK` fontu **yoktur**; daha önce yüklenen Petrel fontu kalabilir. Ayrıca LCD'ye bu paketi yüklemek **yazıcının ana kart firmware'ini geri yüklemez**. Orijinal Creality arayüzünü kullanmak için uyumlu **stok ana kart firmware'ini ayrı olarak** kurmalısınız.

## LCD microSD yuvasından geri yükleme

1. Varsa baskının bitmesini bekleyip yazıcıyı güvenle kapatın. LCD yeniden bağlandığında kaynakları tekrar yazmaması için ana bilgisayardaki **Petrel servisini durdurup devre dışı bırakın**:
   ```bash
   sudo systemctl disable --now Petrel.service
   ```
2. Ekranın orijinal **DWIN T5UIC1** olduğunu doğrulayın. DACAI/TJC ekranlarda veya modelinden emin değilseniz devam etmeyin.
3. Tercihen **8 GB veya daha küçük** güvenilir microSD kartı **MBR**, **FAT32** ve **4096 bayt ayırma birimi** ile biçimlendirin.
4. [Stok `DWIN_SET` klasörünün](../assets/stock-dwin/DWIN_SET) **tamamını** kartın **kök dizinine** kopyalayın. Dizin örneği: `/DWIN_SET/0_start.jpg`, `/DWIN_SET/9.ICO`, `/DWIN_SET/T5UIC1.CFG`. Bunun yerine yalnız Petrel fontunu içeren `assets/fonts/DWIN_SET` klasörünü kullanmayın.
5. **Enerji kesikken**, anakarttaki değil **LCD modülünün arkasındaki microSD yuvasını** kullanın. Kartı takın, ekran bağlantılarını sağlamlaştırın ve enerjiyi verin. Enerji varken kabloları sökmeyin.
6. LCD'nin güncelleme akışını takip edin; uyumlu DWIN ekranlarda gösterge genellikle **mavi → turuncu** olur. İşlem tamamlanmadan enerjiyi kesmeyin.
7. Tekrar kapatın, kartı çıkarın, ekranı toplayın ve normal açın. Uyumlu ana kart firmware'iyle stok açılış görselini ve ikonları kontrol edin.

Güncelleme tamamlanmazsa kart biçimini, kök klasör adını ve ekran modelini kontrol edin; başka bir ekranın paketini denemek yerine farklı microSD kart kullanın. Ek kaynak: [mriscoc DWIN güncelleme rehberi](https://github.com/mriscoc/Ender3V2S1/wiki/How-to-update-the-display).

## Daha sonra Petrel'e geri dönüş

OEM kaynakları korumak istiyorsanız Petrel servisi **kapalı kalmalıdır**. Petrel yeniden etkinleştirildiğinde açılış görselini ve **3** numaralı ikon kütüphanesini tekrar yönetir. SD güncellemesi Flash bloklarını değiştirdiği hâlde Data Flash parmak izleri kalmışsa normal açılış, bazı ikonların veya açılış görselinin hâlâ yüklü olduğunu yanlış varsayabilir. Servis dururken [ikonları açıkça yeniden yükleme işlemini](../assets/README_TR.md#panel-kaynaklarını-yeniden-yükledikten-sonra) uygulayın ve fiziksel ekrandaki açılış görselini ayrıca kontrol edin. Gerekirse [Petrel LCD fontunu](lcd-assets_TR.md#lcd-fontu) yeniden kurun. İkonları yeniden yüklemenin 0 numaralı açılış görselini de zorla yazdığını varsaymayın.

LCD microSD güncellemesi yalnızca **ekranı** değiştirir; Raspberry Pi kurulumunu veya yazıcının ana kartını değiştirmez.
