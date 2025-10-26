document.addEventListener('DOMContentLoaded', () => {
    const menuBtn = document.getElementById('menuBtn');
    const sidenav = document.getElementById('mySidenav');
    const mainContent = document.getElementById('main-content');

    if (menuBtn) {
        menuBtn.addEventListener('click', () => {
            sidenav.classList.toggle('sidenav-open');
            mainContent.classList.toggle('main-content-shifted');
        });
    }
});