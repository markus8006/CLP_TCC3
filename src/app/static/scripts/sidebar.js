document.addEventListener('DOMContentLoaded', () => {
    const menuBtn = document.getElementById('menuBtn');
    const sidenav = document.getElementById('mySidenav');
    const mainContent = document.getElementById('main-content');
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = themeToggle ? themeToggle.querySelector('.theme-icon') : null;
    const sidenavBackdrop = document.getElementById('sidenavBackdrop');
    const docEl = document.documentElement;
    const storageKey = 'preferredTheme';

    const safeGetItem = (key) => {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return null;
        }
    };

    const safeSetItem = (key, value) => {
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            /* ignore storage errors */
        }
    };

    const applyTheme = (theme) => {
        const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
        docEl.setAttribute('data-theme', normalizedTheme);
        safeSetItem(storageKey, normalizedTheme);

        if (themeIcon) {
            themeIcon.textContent = normalizedTheme === 'dark' ? '🌙' : '☀️';
        }

        if (themeToggle) {
            themeToggle.setAttribute(
                'aria-label',
                normalizedTheme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'
            );
        }
    };

    const storedTheme = safeGetItem(storageKey);
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = storedTheme || docEl.getAttribute('data-theme') || (prefersDark ? 'dark' : 'light');
    applyTheme(initialTheme);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = docEl.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(nextTheme);
        });
    }

    const applyNavState = (isOpen) => {
        if (!sidenav || !mainContent) {
            return;
        }

        sidenav.classList.toggle('sidenav-open', isOpen);
        mainContent.classList.toggle('main-content-shifted', isOpen);

        const shouldLockViewport = isOpen && window.innerWidth <= 992;
        document.body.classList.toggle('nav-open', shouldLockViewport);

        if (menuBtn) {
            menuBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        }

        sidenav.setAttribute('aria-hidden', isOpen ? 'false' : 'true');

        if (sidenavBackdrop) {
            sidenavBackdrop.hidden = !shouldLockViewport;
            sidenavBackdrop.classList.toggle('active', shouldLockViewport);
        }
    };

    const toggleNav = () => {
        if (!sidenav) {
            return;
        }

        const isOpen = !sidenav.classList.contains('sidenav-open');
        applyNavState(isOpen);
    };

    const closeNav = () => applyNavState(false);

    if (menuBtn && sidenav && mainContent) {
        menuBtn.addEventListener('click', toggleNav);
    }

    if (sidenavBackdrop) {
        sidenavBackdrop.addEventListener('click', closeNav);
    }

    if (sidenav) {
        sidenav.setAttribute('aria-hidden', 'true');
        sidenav.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeNav();
            }
        });

        const navLinks = Array.from(sidenav.querySelectorAll('a'));
        navLinks.forEach((link) => {
            link.addEventListener('click', () => {
                if (window.innerWidth <= 992) {
                    closeNav();
                }
            });
        });
    }

    window.addEventListener('resize', () => {
        if (!sidenav) {
            return;
        }

        const isOpen = sidenav.classList.contains('sidenav-open');
        applyNavState(isOpen);
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && sidenav && sidenav.classList.contains('sidenav-open')) {
            closeNav();
        }
    });

    applyNavState(false);
});
