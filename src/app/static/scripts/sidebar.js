const initializeSidebar = () => {
    const menuBtn = document.getElementById('menuBtn');
    const sidenav = document.getElementById('mySidenav');
    const mainContent = document.getElementById('main-content');
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = themeToggle ? themeToggle.querySelector('.theme-icon') : null;
    const docEl = document.documentElement;
    const bodyEl = document.body;
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
        if (bodyEl) {
            bodyEl.setAttribute('data-theme', normalizedTheme);
        }
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

    if (menuBtn && sidenav && mainContent) {
        menuBtn.addEventListener('click', () => {
            sidenav.classList.toggle('sidenav-open');
            mainContent.classList.toggle('main-content-shifted');
        });
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSidebar, { once: true });
} else {
    initializeSidebar();
}
