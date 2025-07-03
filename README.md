# AzuraForge Worker Servisi

Bu servis, AzuraForge platformunun ağır iş yükünü taşıyan, arka plan görevlerini işleyen motorudur.

## 🎯 Ana Sorumluluklar

1.  **Görev İşleyici (Celery Worker):**
    *   `Redis`'teki görev kuyruğunu dinler ve `API` tarafından gönderilen yeni görevleri (örn: model eğitimi) alır.
    *   Python `entry_points` mekanizması ile platforma "eklenti" olarak kurulan AI pipeline'larını (`azuraforge-app-*`) keşfeder ve çalıştırır.

2.  **Raporlama ve Sonuç Üretimi:**
    *   Tamamlanan her deneyin sonuçlarını ve meta verilerini `PostgreSQL` veritabanına yazar.

3.  **Redis Pub/Sub Yayıncısı:**
    *   Eğitim sırasında, `RedisProgressCallback` aracılığıyla, anlık ilerleme verilerini (epoch, kayıp değeri vb.) ilgili Redis kanalına (`task-progress:*`) yayınlayarak `API` servisinin canlı takip yapmasını sağlar.

---

## 🏛️ Ekosistemdeki Yeri

Bu servis, AzuraForge ekosisteminin bir parçasıdır. Projenin genel mimarisini, vizyonunu ve geliştirme rehberini anlamak için lütfen ana **[AzuraForge Platform Dokümantasyonuna](https://github.com/AzuraForge/platform/tree/main/docs)** başvurun.

---

## 🛠️ Yerel Geliştirme ve Test

Bu servisi yerel ortamda çalıştırmak ve test etmek için, ana `platform` reposundaki **[Geliştirme Rehberi](https://github.com/AzuraForge/platform/blob/main/docs/DEVELOPMENT_GUIDE.md)**'ni takip ederek genel ortamı kurun.

Sanal ortam aktive edildikten sonra, bu repo dizinindeyken aşağıdaki komutla Worker'ı başlatabilirsiniz:

```bash
# worker/ kök dizinindeyken
start-worker
```

Worker, Redis'e bağlanacak ve yeni görevleri beklemeye başlayacaktır. Birim testlerini çalıştırmak için `pytest` komutunu kullanın.

