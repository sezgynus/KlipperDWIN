# Maintenance test planlayıcısı (geliştirme)

[English](maintenance-test-planner.md) · [Katalog](maintenance-test-catalog_TR.md)

**Durum:** Yalnız saf planlama var. Yazıcı veya LCD kontrol edilmez; menü hâlâ placeholder durumunda.

`maintenance_planner.build_plan(snapshot, adapters=())`, değişmez keşif snapshot'ını 121-ID kataloğu ve **açıkça kayıtlı** adaptörlerle kesiştirir. Varsayılan adaptör kayıt listesi boştur; bu nedenle keşfedilen bütün adaylar `blocked` kalır ve `visible_plan` boş döner. Keşif yöntemi tek başına test adaptörü kurmaz.

Her değişmez satırda özellik ID'si, tam cihaz veya global kapsam, olası yöntem maskesi, seçili tek yöntem, varsa kayıtlı adaptör adı, gerekli kanıt, güvenlik profili anahtarı, Klipper epoch/config işareti ve atanmış rezonans eksenleri bulunur. Birden fazla heater, fan ve TMC ayrı kalır. R02/R03/R04 yalnız gerçekten atanmış ivmeölçer/eksen örneklerine bağlanır; yinelenen global satır üretilmez.

Kayıtlı yöntemler tam eşleşmeyle seçilir ve katalog, kanıt ve güvenlik profiliyle karşılaştırılır; sahte kayıtlar, tekrarlar, desteklenmeyen ID'ler ve geçersiz maskeler reddedilir. Kayıtlı `INFORMATION` yöntemi yalnız bilgi satırı oluşturur, **PASS üretmez**. Yönlendirmeli yöntem kullanıcı/alet/kalibrasyon etkileşimi gerektirir. `runnable` adlı aday bile **komut gönderme izni değildir**: gelecekteki Safety Coordinator anlık yazıcı ve komut öncesi güvenliği doğrulamalı, Executor da gerçek ölçümleri değerlendirmelidir.

I/O, G-code, polling, worker, abonelik, çizim kodu veya mevcut `PrinterCapabilities` üzerinde değişiklik yoktur. GitHub Actions, branch push'unda `tests/test_maintenance_planner.py` dosyasını tam regresyon paketiyle çalıştırır; yeni adıma geçmeden imzalı HEAD ve CI PASS doğrulanır.
