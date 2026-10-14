# LCD uyumluluğu

[English](lcd-assets.md) · [Türkçe](lcd-assets_TR.md) · [Dokümantasyon](README_TR.md)

## Desteklenen ekran

Petrel, uyumlu 4,3 inç Ender 3 V2 panelinde kullanılan **272×480 dikey DWIN T5UIC1** düzenini hedefler. DWIN, DACAI ve TJC firmware/kaynak paketleri birbirinin yerine kullanılamaz.

Panel, T5UIC1 komutlarını ve ekran yönü **1** düzenini desteklemelidir. Petrel yazıları native fontla çizer; [LCD fontunu](#lcd-fontu) SD karttan kurun. Uygulama açılış görselini ve library **3** ikonlarını repo kaynaklarından otomatik yükler; stok `3.ICO` veya İngilizce bitmap yazılar önkoşul değildir.

## Panel kurmadan veya değiştirmeden önce

Yalnız ekran boyutunu değil, kontrolcü ailesini ve kurulu kaynak paketini kontrol edin. Uygulama kurulum betiği LCD kernel firmware'ini veya LCD fontunu yüklemez. Panel firmware çalışmaları için isteğe bağlı [T5UIC1 referansını](t5uic1-reference.md) kullanın.

Kurulumdan sonra fiziksel ekranda menü yazılarını/ikonlarını, renkleri, önizlemeleri ve encoder gezinmesini inceleyin. Çalışan emülatör görüntüsü farklı panel/kaynak paketinde aynı görünümü garanti etmez.

## Baskı önizlemeleri

Önizlemeler Moonraker'dan gelir ve yeni panel kaynak paketi gerektirmez. Eksik thumbnail baskı başlatmayı engellemez. Görseller yeniden başlatma veya yeniden bağlantı sonrası tekrar hazırlanır; kurulu ikonların yerine geçmez. Thumbnail’ler kalite 94 baseline 4:2:0 JPEG, siyah zemin ve panelin gelişmiş arka plan filtresini kullanır. Modelin koyu pikselleri alpha birleştirmesinden önce en az 48 parlaklık seviyesine yükseltilir; saf siyah koyu gri olur. Tam şeffaf pikseller ve kenar boşlukları siyah kalır, filtrelenince UI zemini görünür. Yarı şeffaf kenarlar panel filtresinde kesilebilir; fiziksel ekranda kontrol edin.

## Kaynakları tanıma

Uygulama artık kütüphane 3'yi [`assets/icons`](../assets/icons/README_TR.md) kaynaklarından oluşturur ve güncelleme sonrası ilk LCD bağlantısında değişen blokları otomatik yükler. Değişmeyen kaynaklar atlanır. JPEG ekleme, paketi dışa aktarma ve panel kaynakları yeniden kurulduktan sonra zorla yükleme için bu kılavuzu kullanın.

Normal kullanımda otomatik eşitleme yeterlidir. Geliştirici tanılaması için aşağıdaki komut güncel `assets/icons` JPEG kaynaklarından paketi yeniden oluşturup UART üzerinden yükler; referans ICO dosyasını okumaz:

```sh
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py && sudo systemctl start Petrel.service
```

Araç yapılandırılmış seri portu kullanır ve 3’ten başlayan slotlara yazar (her 32 KiB blok için bir slot). Yazma başarısız olursa servis kapalı kalır. Yazma onayları kontrol edilir; Flash geri okuması yapılmaz. Yüklemeden sonra ikonları fiziksel panelde kontrol edin.

Referans export dosyasının kendisini incelemek için servis kapalıyken açıkça `--file` verin. Aşağıdaki işlem, JPEG kaynaklarından yeniden paketlemek yerine belirtilen dosyanın baytlarını yükler; kaynaklar değiştiyse bu referans dosya farklı veya eski olabilir:

```sh
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py --file ~/Petrel/assets/emulator/3.ICO && sudo systemctl start Petrel.service
```

Katkı görselleri için `tools/pack_icon_library.py kaynak.ICO hedef.ICO --library 3`, JPEG görsellerini koruyarak her ikonu tek bir 32 KiB blokta tutar. Böylece gözlenen çizim sorunlarıyla ilişkili blok sınırlarında ikonların bölünmesi önlenir.

[Stok envanteri](lcd-assets.json) proje için önceden incelenen kaynakları kaydeder. Kendi panelinizde kurulu dosyaları belirlemez. Katkı görselleri ve emülatör font seçimi talimatlarına [dokümantasyon dizininden](README_TR.md) ulaşabilirsiniz.

## LCD fontu

İkon kütüphanesi UART üzerinden otomatik güncellenir. Petrel ile aynı yazı görünümü için `assets/fonts/DWIN_SET/0T5UIC1.HZK` içindeki ASCII fontunu da LCD’nin SD kart kaynak güncelleme yöntemiyle kurun. Depodaki `DWIN_SET` klasörünü uyumlu LCD güncelleme kartına kopyalayın, yazıcıyı kapatın, kartı LCD’nin kart okuyucusuna takın, enerjiyi verin ve kaynak güncellemesi bitene kadar bekleyin. Yazıcıyı kapatıp kartı çıkarın ve normal başlatın. Pi servisi font Flash’ını UART üzerinden yüklemez. Emülatör aynı fontu kullanır; DejaVu lisansı `assets/emulator/Petrel-font-license.txt` içindedir.
