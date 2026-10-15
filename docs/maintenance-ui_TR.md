# Aşama 8D: Graphite Maintenance UI

[English](maintenance-ui.md)

Maintenance ekranına giriş pasiftir: **Self Tests** ve **Diagnostics** hiçbir GET veya fiziksel komut olmadan görüntülenir. Self Tests sadece Aşama 8'in gerçekten keşfettiği güvenilir hedefleri, Diagnostics ise salt-okunur adaptörleri listeler. Desteklenmeyen donanım varmış gibi gösterilmez.

Self Test için tam cihaz seçilir, sınırlı salt-okunur güvenlik/kuyruk/başlangıç değeri ön kontrolünün bitmesi beklenir. Varsayılan **Cancel** seçeneğinden enkoderle **Run short pulse** seçilir ve üç saniye içinde basılarak açık onay verilir. Test sırasında backend kısa geri yüklemeli script'i gönderir ve ardından çıktıyı yeniden okur. Başlangıç değerine döndüğü doğrulanırsa ayrıca **Did it work?** sorulur; varsayılan **Not observed** seçimidir ve `PASSED_USER` için kullanıcı bilerek **Yes, observed** seçmelidir. Doğrulama hatası, fan hareketi veya ışık gözlenmiş olsa bile `INCONCLUSIVE` üretir. Fiziksel RPM ölçülmüş sayılmaz. Belirsiz komut UI tarafından yeniden gönderilmez.

Ekranda dolaşma, menüye giriş ve tekrar çizim fiziksel pulse başlatmaz. Başlangıç durumu/config/profil olumlu doğrulanamayan çıkışların fiziksel testi kapalı kalır. Güvenli salt-okunur Diagnostics bu aktüatör testlerinden bağımsız kullanılabilir.

CI; sahte Moonraker ve mock LCD ile enkoder navigasyonu ve komutsuz menü girişini denetler. Gerçek fan, LED, buzzer ve case-light testleri donanım kabulü sayılmadan önce kullanıcı tarafından güvenli boşta yazıcıda açıkça başlatılıp gözlenmelidir.
