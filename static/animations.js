/* ==========================================================================
   animations.js - Anti-Gravity Engine & IntersectionObserver Logic
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {

    // 1. SCROLL NAVBAR
    const navbar = document.querySelector('.navbar-ctf');
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 80) {
                navbar.classList.add('scrolled-nav');
            } else {
                navbar.classList.remove('scrolled-nav');
            }
        });
    }

    // 2. CARD SCROLL-IN
    const ctfCards = document.querySelectorAll('.ctf-card');
    if (ctfCards.length > 0 && typeof IntersectionObserver !== 'undefined') {
        const cardObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('card-visible');
                    cardObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });

        ctfCards.forEach((card, index) => {
            // Apply a staggered delay based on its DOM index among .ctf-card elements
            card.style.transitionDelay = `${index * 80}ms`;
            cardObserver.observe(card);
        });
    }

    // 3. BUTTON RIPPLE
    const buttons = document.querySelectorAll('.btn-ctf, .btn-ctf-full');
    buttons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const ripple = document.createElement('span');
            ripple.classList.add('ripple-circle');
            ripple.style.left = `${x}px`;
            ripple.style.top = `${y}px`;
            ripple.style.width = '2px';
            ripple.style.height = '2px';
            
            this.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    });

    // 4. SCORE COUNTUP
    const scoreElements = document.querySelectorAll('[data-score]');
    if (scoreElements.length > 0 && window.countUp) {
        const scoreObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const el = entry.target;
                    const score = parseInt(el.getAttribute('data-score')) || 0;
                    if (!el.classList.contains('counted')) {
                        const counter = new window.countUp.CountUp(el, score, { duration: 2 });
                        if (!counter.error) {
                            counter.start();
                        }
                        el.classList.add('counted');
                    }
                    scoreObserver.unobserve(el);
                }
            });
        }, { threshold: 0.5 });

        scoreElements.forEach(el => scoreObserver.observe(el));
    }


    // 6. FLASH AUTO-DISMISS
    const flashes = document.querySelectorAll('.alert-ctf');
    if (flashes.length > 0) {
        setTimeout(() => {
            flashes.forEach(flash => {
                flash.classList.add('alert-slideout');
            });
        }, 4000);
    }

    // 7. GSAP ENHANCEMENT
    if (typeof gsap !== 'undefined') {
        if (typeof ScrollTrigger !== 'undefined') {
            gsap.registerPlugin(ScrollTrigger);
        }
        
        // Removed gsap.from('.ctf-card') because it conflicts with the IntersectionObserver and CSS opacity=0.
        // The IntersectionObserver handles the card scroll-in perfectly.
        
        const headings = document.querySelectorAll('h1, h2');
        if (headings.length > 0) {
            gsap.from(headings, {
                duration: 0.6,
                filter: "blur(12px)",
                opacity: 0
            });
        }
    }

    // 8. VANTA NET
    const vantaBg = document.getElementById('vanta-bg');
    if (vantaBg && typeof window.VANTA !== 'undefined') {
        window.VANTA.NET({
            el: "#vanta-bg",
            color: 0x00e676,
            backgroundColor: 0x03060b,
            points: 8,
            maxDistance: 18,
            spacing: 18
        });
    }

    // 9. NAVBAR BRAND RE-ANIMATE
    const navBrand = document.querySelector('.navbar-brand');
    if (navBrand && typeof gsap !== 'undefined') {
        navBrand.addEventListener('mouseenter', () => {
            gsap.to(navBrand, {
                scaleX: 1.02,
                color: "#00ff9f",
                duration: 0.1,
                yoyo: true,
                repeat: 1,
                onComplete: () => {
                    gsap.set(navBrand, { clearProps: "all" });
                }
            });
        });
    }

    // 10. PERFORMANCE
    if (window.innerWidth < 768 && typeof tsParticles !== 'undefined') {
        setTimeout(() => {
            if (tsParticles.domItem && tsParticles.domItem(0)) {
                const pContainer = tsParticles.domItem(0);
                if (pContainer && pContainer.options) {
                    pContainer.options.particles.number.value = 25;
                    pContainer.refresh();
                }
            }
        }, 1000);
    }
});
