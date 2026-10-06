// Generated from src/startup.ts by build.mjs.
(function begin() {
        if (typeof document === "undefined")
            return;
        try {
            const theme = window.localStorage.getItem("av-theme");
            if (theme === "light" || theme === "dark")
                document.documentElement.setAttribute("data-theme", theme);
        }
        catch { /* storage unavailable: the system preference applies */ }
    })();
