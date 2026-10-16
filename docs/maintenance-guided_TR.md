# Maintenance Aşama 8 — yönlendirmeli donanım gözlem sözleşmeleri

[English](maintenance-guided.md)

Bu **Aşama 8A: güvenilir hedefler ve kullanıcı onayı** katmanıdır; henüz fiziksel aktüasyon değildir.

`maintenance_guided.guided_plan(snapshot)`, mevcut değişmez discovery/catalog/planner kayıtlarını birleştirip yalnız tam eşleşen USER yöntemi adaylarını sunar: `F01` RPM'siz stok part fan, `F04` gerçekten keşfedilmiş fan_generic örnekleri, `O04` adlandırılmış LED cihazları, `O03` açıkça `visual` rolü verilen ve `maintenance.visual:<nesne>` kanıtı bulunan her `output_pin` ile `S18` açıkça `audible` rolü verilen ve `maintenance.audible:<nesne>` kanıtı bulunan her `pwm_cycle_time`. Rastgele `output_pin`, heater fan, controller fan, servo, macro, bilinmeyen fan ya da sahte takometre bu listeye giremez. Donanım fiziksel olarak takılı olsa dahi servis kanıtı eksikse aday gösterilmez.

`GuidedConsentGate`, tam eşleşen kayıtlı hedefi, güncel READY epoch/config durumunu ve *olumlu doğrulanmış* iş kuyruğu ile Petrel operasyon kontrollerini içeren fail-closed `MaintenanceSafetyCoordinator` koşullarını denetler. Açık kullanıcı isteğini kaydeder ancak hiçbir komutu çalıştıramaz veya kuyruğa alamaz. Tek olumlu terminal kayıt `CONSENTED / no_hardware_command_dispatched` şeklindedir. Onay; motor dönmesi, ışık yanması, ses duyulması veya fiziksel PASS kanıtı değildir.

Sonraki aşamada ayrı ve küçük bir izin listeli komut adaptörü uygulanmalı, her yazmadan hemen önce kuyruk/operasyon güvenlik kanıtı tekrar denetlenmeli, uygun hedeflerde başlangıç durumu kaydedilmeli, yürütme ve hata/kopma durumunda temizleme sınırlı ve doğrulanmış olmalı, ancak sonra kullanıcı gözlem kanıtı istenmelidir. Komutlanan PWM ile ölçülen RPM ayrı tutulmalıdır. Güvenli geri alma tanımlanamayan bütün profiller engellenmelidir.

Aşama 8A'da UI entegrasyonu, endpoint polling, arka plan worker'ı, kullanıcıya sunulan test, fiziksel komut veya normal baskı sıcak yolunda değişiklik yoktur. Regresyon: `tests/test_maintenance_guided.py`.
