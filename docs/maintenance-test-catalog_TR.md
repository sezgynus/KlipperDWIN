# Maintenance test kataloğu (geliştirme)

[English](maintenance-test-catalog.md) · [Keşif](maintenance-discovery_TR.md) · **[Referans yazıcı fiziksel kabul çizelgesi](maintenance-reference-printer-acceptance_TR.md)**

**Güncel uygulama notu:** Bu dosya statik katalog katmanını açıklar. Daha sonra F01, F04, O03, O04 ve S18 için ayrı fiziksel adaptörler uygulanmıştır. Kullanıcının gerçekten onayladığı cihaz bazlı testler bağlantılı referans yazıcı çizelgesinde izlenir. Katalog satırı tek başına yürütme izni veya fiziksel PASS değildir.

`maintenance_catalog.py`, kararlaştırılmış 121 özellik ID'sinin tümü için açıklama, global/cihaz/karma kapsam, olası keşif yöntemleri, gerekli kanıt tanımlayıcısı ve güvenlik profili sınıfını taşıyan küçük ve değişmez tablodur. Doğrulanmış adaptör daha sonraki aşamada uygulanıp kaydedilene kadar her `adapter_id` değeri `None` kalır. Bilerek gizlenen sekiz ID gizli kalır. Bilinmeyen veya standart dışı ID'ler güvenli biçimde reddedilir.

Katalogdaki yöntem maskesi üst sınırdır: `candidate_methods(id, discovery_mask)` yalnız olası yöntemlerin kesişimini döndürür. Bu işlem **güvenlik izni, başarılı ölçüm veya mevcut bir yürütücü kanıtı değildir**. `INFORMATION` bir işlev PASS'i değil, izlemedir. Kanıt tanımlayıcıları gelecekte gereken delili belgeler; örnekleme veya doğrulamayı kendileri gerçekleştirmez.

Sonraki Planner katmanı cihaz ve global keşif sonuçlarını doğru eşlemeli, açıkça kayıtlı adaptör ve kanıt doğrulayıcısı aramalı, uygun olmayan/engellenen testleri etkin menüye almamalıdır. Ayrı Safety Coordinator, yan etkili her komut öncesinde yazıcı durumunu pozitif olarak yeniden doğrulamalıdır. Bu katalog keşif modüllerini, yazıcı telemetri sıcak yolunu, normal UI'yi veya `PrinterCapabilities` sınıfını değiştirmez.

`Driver Branch Regression` GitHub Actions iş akışı, her branch push'unda `tests/test_maintenance_catalog.py` testlerini mevcut regresyon paketiyle birlikte çalıştırır. Geliştirme iş akışında lokal test çalıştırılmaz. Son imzalı branch HEAD ve ona ait CI sonucu doğrulanmadan sonraki aşamaya geçilmez.
