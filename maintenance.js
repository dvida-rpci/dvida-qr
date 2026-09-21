(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var btnFicha = document.getElementById('btn-ver-ficha');
        var btnHistorial = document.getElementById('btn-ver-historial');
        var fichaView = document.getElementById('ficha-view');
        var historialView = document.getElementById('historial-view');

        if (!btnFicha || !btnHistorial || !fichaView || !historialView) {
            // Página sin ficha de TAG (home o índice de categoría) — no hay nada que hacer acá.
            return;
        }

        function showFicha() {
            fichaView.hidden = false;
            historialView.hidden = true;
            btnFicha.classList.add('active');
            btnFicha.setAttribute('aria-selected', 'true');
            btnHistorial.classList.remove('active');
            btnHistorial.setAttribute('aria-selected', 'false');
        }

        function showHistorial() {
            fichaView.hidden = true;
            historialView.hidden = false;
            btnHistorial.classList.add('active');
            btnHistorial.setAttribute('aria-selected', 'true');
            btnFicha.classList.remove('active');
            btnFicha.setAttribute('aria-selected', 'false');
        }

        btnFicha.addEventListener('click', showFicha);
        btnHistorial.addEventListener('click', showHistorial);
    });
})();
