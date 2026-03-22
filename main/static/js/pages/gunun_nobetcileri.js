document.addEventListener("DOMContentLoaded", function() {
    const selects = document.querySelectorAll('.smart-select');
    let isDirty = false;

    function updateAvailability() {
        const selectedValues = new Set();
        selects.forEach(s => { if (s.value) selectedValues.add(s.value); });

        selects.forEach(s => {
            const currentVal = s.value;
            Array.from(s.options).forEach(opt => {
                if (!opt.value) return;
                // Eğer değer listede varsa VE bu kutunun kendi seçimi değilse -> Pasif yap
                if (selectedValues.has(opt.value) && opt.value !== currentVal) {
                    opt.disabled = true;
                    // İsteğe bağlı: grileşen seçeneğin yanına (Dolu) yazılabilir
                } else {
                    opt.disabled = false;
                }
            });
        });
    }

    // İlk yükleme ve her değişiklikte çalıştır
    updateAvailability();
    selects.forEach(s => {
        s.addEventListener('change', function() {
            updateAvailability();
            isDirty = true;
        });
    });

    window.addEventListener('beforeunload', function (e) {
        if (isDirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    const form = document.querySelector('form[method="post"]');
    if (form) {
        form.addEventListener('submit', function() {
            isDirty = false;
        });
    }
});
