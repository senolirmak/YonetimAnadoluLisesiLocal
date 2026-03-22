document.addEventListener("DOMContentLoaded", function() {
    const selects = document.querySelectorAll('.lesson-select');

    function updateOptions(hour) {
        // İlgili saatteki tüm kutuları bul
        const hourSelects = document.querySelectorAll(`.lesson-select[data-hour="${hour}"]`);
        const selectedValues = new Set();
        
        // Hangi derslerin seçildiğini topla
        hourSelects.forEach(s => {
            if (s.value) selectedValues.add(s.value);
        });

        // Her kutu için seçenekleri güncelle
        hourSelects.forEach(s => {
            const currentVal = s.value; // Kutunun kendi seçili değeri
            Array.from(s.options).forEach(opt => {
                if (!opt.value) return; // Boş seçeneği atla
                
                // Eğer değer listede varsa VE bu kutunun kendi seçimi değilse -> Pasif yap
                if (selectedValues.has(opt.value) && opt.value !== currentVal) {
                    opt.disabled = true;
                } else {
                    opt.disabled = false;
                }
            });
        });
    }

    // Sayfa yüklendiğinde mevcut duruma göre ayarla
    for (let h = 1; h <= 8; h++) updateOptions(h);

    // Her değişiklikte tekrar hesapla
    selects.forEach(s => {
        s.addEventListener('change', function() { updateOptions(this.getAttribute('data-hour')); });
    });
});
