# LCD uyumluluğu

[English](lcd-assets.md) · [Türkçe](lcd-assets_TR.md) · [Dokümantasyon](README_TR.md)

## Desteklenen ekran

KlipperDWIN, uyumlu 4,3 inç Ender 3 V2 panelinde kullanılan **272×480 dikey DWIN T5UIC1** düzenini hedefler. DWIN, DACAI ve TJC firmware/kaynak paketleri birbirinin yerine kullanılamaz.

Fiziksel panelde eşleşen stok ikon kütüphanesi **7 (`7.ICO`)**, fontlar ve İngilizce bitmap kaynakları bulunmalıdır. Ekran yönü **1**'dir. Özel KlipperDWIN görselleri uygulamayla ayrıca sağlanır; [görsel rehberine](../assets/README_TR.md) bakın.

## Panel kurmadan veya değiştirmeden önce

Yalnız ekran boyutunu değil, kontrolcü ailesini ve kurulu kaynak paketini kontrol edin. Uygulama kurulum betiği LCD kernel firmware'ini veya stok font/ikon paketini yüklemez. Panel firmware çalışmaları için isteğe bağlı [T5UIC1 referansını](t5uic1-reference.md) kullanın.

Kurulumdan sonra fiziksel ekranda menü yazılarını/ikonlarını, renkleri, önizlemeleri ve encoder gezinmesini inceleyin. Çalışan emülatör görüntüsü farklı panel/kaynak paketinde aynı görünümü garanti etmez.

## Baskı önizlemeleri

Önizlemeler Moonraker'dan gelir ve yeni panel kaynak paketi gerektirmez. Eksik thumbnail baskı başlatmayı engellemez. Görseller yeniden başlatma veya yeniden bağlantı sonrası tekrar hazırlanır; kurulu ikonların yerine geçmez.

## Kaynakları tanıma

[Stok envanteri](lcd-assets.json) proje için önceden incelenen kaynakları kaydeder. Kendi panelinizde kurulu dosyaları belirlemez. Katkı görselleri ve emülatör font seçimi talimatlarına [dokümantasyon dizininden](README_TR.md) ulaşabilirsiniz.
