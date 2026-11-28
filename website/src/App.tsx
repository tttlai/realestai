import { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, ChevronRight, Menu, X, Lightbulb } from 'lucide-react';
import Lamp from './Lamp';

const consultationLink = 'https://cal.com/trishal-suvarna-zo4ibc/30min';
const newTab = { target: '_blank', rel: 'noopener noreferrer' };

const navLinks = [
  { label: 'Products', href: '#products' },
  { label: 'Services', href: '#services' },
  { label: 'About', href: '#about' },
  { label: 'Contact', href: '#contact' },
];

// Ready-to-use products, right under the hero.
const products = [
  {
    title: 'WhatsApp Assistant for Property Brokers',
    description:
      'Answers property enquiries day or night, finds out what buyers need, and alerts you when someone wants a visit',
    href: '/brokers/', // the static page in public/brokers/
    cta: 'See how it works',
    external: false,
  },
  {
    title: 'RealAssist for Landlords',
    description:
      'Property management for Indian landlords and NRIs: AI rent estimates, rent collection, WhatsApp reminders and tax reports',
    href: 'https://www.realassist.in/',
    cta: 'Visit realassist.in',
    external: true,
  },
];

// Custom work, each with one example.
const services = [
  {
    title: 'AI Customer Service',
    description: 'Intelligent agents that handle customer inquiries 24/7 with human-like understanding',
    example: 'Instant WhatsApp replies to guests, with PDFs shared automatically',
  },
  {
    title: 'Workflow Automation',
    description: 'Smart agents that streamline and automate your business processes end-to-end',
    example: 'Booking calendars synced across platforms, payments verified, and check-in codes sent to smart locks',
  },
  {
    title: 'Appointment Scheduling',
    description: 'Smart scheduling for service-based businesses',
    example: 'Suggests the best time slots, sends reminders and handles rescheduling',
  },
  {
    title: 'Custom AI Agents & Documentation',
    description: 'Tailored AI agents designed for your specific business needs and objectives',
    example: 'Technical documentation that is generated, updated and maintained automatically',
  },
];

function Logo() {
  return (
    <a href="#top" className="inline-flex items-center gap-2 py-2 text-snow">
      <Lightbulb className="h-7 w-7 text-mint" aria-hidden="true" />
      <span className="font-display text-xl font-bold tracking-wider">REALEST AI</span>
    </a>
  );
}

function App() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const closeMenu = () => setIsMenuOpen(false);

  // The browser looks for a link's #section before React has drawn it (e.g. /#services).
  useEffect(() => {
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ behavior: 'instant' });
  }, []);

  return (
    <div id="top">
      <header className="sticky top-0 z-50 bg-night text-night-text">
        <nav className="wrap flex min-h-[72px] items-center justify-between" aria-label="Main">
          <Logo />

          <div className="hidden items-center gap-9 md:flex">
            {navLinks.map(({ label, href }) => (
              <a key={label} href={href} className="py-3 hover:text-mint">
                {label}
              </a>
            ))}
            <a
              href={consultationLink}
              {...newTab}
              className="rounded-lg border border-mint px-5 py-2.5 font-bold text-mint hover:bg-mint hover:text-night"
            >
              Schedule a Call
            </a>
          </div>

          <button
            type="button"
            className="-mr-3 p-3 text-snow md:hidden"
            aria-label={isMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={isMenuOpen}
            aria-controls="mobile-menu"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
          >
            {isMenuOpen ? <X /> : <Menu />}
          </button>
        </nav>

        <div id="mobile-menu" hidden={!isMenuOpen} className="border-t border-night-raised md:hidden">
          <div className="wrap flex flex-col py-4">
            {navLinks.map(({ label, href }) => (
              <a key={label} href={href} className="py-3 text-xl" onClick={closeMenu}>
                {label}
              </a>
            ))}
            <a
              href={consultationLink}
              {...newTab}
              className="mt-3 rounded-lg bg-mint px-5 py-4 text-center font-bold text-night"
              onClick={closeMenu}
            >
              Schedule a Call
            </a>
          </div>
        </div>
      </header>

      <main>
        <section className="-mt-px overflow-hidden bg-night text-night-text">
          <div className="wrap relative flex flex-col justify-end pb-14 pt-[216px] md:min-h-[max(620px,calc(100svh-72px))] md:justify-center md:py-20">
            <Lamp className="pointer-events-none absolute -right-8 top-0 w-[190px] md:right-[-60px] md:w-[min(46vw,540px)]" />
            <div className="rise relative md:max-w-[56%] lg:max-w-[620px]">
              <h1 className="text-[clamp(2.75rem,1.6rem+4.9vw,5.2rem)] leading-none text-snow [text-wrap:wrap]">
                Real AI Solutions for Real Business Growth
              </h1>
              <p className="mt-7 max-w-[40ch] text-xl leading-relaxed">
                Transform your business operations with cutting-edge AI solutions. We build custom automation systems that scale with your needs.
              </p>
              <a href={consultationLink} {...newTab} className="button mt-9 bg-mint text-night">
                Schedule a Consultation
                <ArrowRight aria-hidden="true" />
              </a>
            </div>
          </div>
        </section>

        <section id="products" className="section wrap">
          <h2 className="section-title">Our Products</h2>
          <p className="mt-3 text-xl text-ink-soft">Ready to use today.</p>
          <ul className="mt-8 grid gap-4 md:mt-10 md:gap-5 lg:grid-cols-2">
            {products.map(({ title, description, href, cta, external }) => (
              <li key={title}>
                <a
                  href={href}
                  {...(external ? newTab : {})}
                  className="flex h-full flex-col gap-4 rounded-2xl bg-mint-soft p-6 hover:bg-mint md:gap-6 md:p-11"
                >
                  <div>
                    <h3 className="text-[clamp(1.7rem,1.3rem+1.6vw,2.5rem)]">{title}</h3>
                    <p className="mt-3 max-w-[52ch]">{description}</p>
                  </div>
                  <span className="mt-auto inline-flex items-center gap-1 font-bold">
                    {cta}
                    {external ? (
                      <ArrowUpRight className="arrow" aria-hidden="true" />
                    ) : (
                      <ChevronRight className="arrow" aria-hidden="true" />
                    )}
                  </span>
                </a>
              </li>
            ))}
          </ul>

        </section>

        <section id="services" className="section bg-night text-night-text">
          <div className="wrap">
            <h2 className="section-title text-snow">What We Build</h2>
            <p className="mt-3 text-xl">Custom AI and automation, built around your business.</p>
            <ul className="mt-8 grid gap-4 md:mt-10 md:grid-cols-2 md:gap-5">
              {services.map(({ title, description, example }) => (
                <li key={title} className="rounded-2xl bg-night-raised p-6 md:p-9">
                  <h3 className="text-[clamp(1.4rem,1.2rem+1vw,2rem)] text-snow">{title}</h3>
                  <p className="mt-2 text-base leading-normal md:mt-3 md:text-lg">{description}</p>
                  <p className="mt-4 border-t border-[#2c4468] pt-3 text-base leading-normal md:mt-5 md:pt-4 md:text-lg">
                    <span className="font-bold text-mint">For example: </span>
                    {example}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="about" className="section">
          <div className="wrap grid gap-8 md:grid-cols-[1.15fr_1fr] md:gap-20">
            <h2 className="section-title">Pioneering the Future of Business Automation</h2>
            <p className="max-w-[48ch] text-xl leading-relaxed text-ink-soft">
              We're not just another automation company. We're pioneers in combining artificial intelligence with business processes to create seamless, efficient, and intelligent workflows that transform how businesses operate.
            </p>
          </div>
        </section>

        <section id="contact" className="section bg-mint">
          <div className="wrap grid gap-8 md:grid-cols-[1.5fr_1fr] md:items-end md:gap-20">
            <h2 className="text-[clamp(2.5rem,1.5rem+4.4vw,5rem)] leading-none">Ready to Transform Your Business?</h2>
            <div>
              <p className="max-w-[40ch] text-xl">
                Join the hundreds of businesses already leveraging our AI solutions to stay ahead of the competition.
              </p>
              <a href={consultationLink} {...newTab} className="button mt-7 bg-night text-snow">
                Schedule a Demo
                <ArrowRight aria-hidden="true" />
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-night pb-10 pt-16 text-night-text">
        <div className="wrap">
          <div className="grid gap-10 sm:grid-cols-2 md:grid-cols-[2fr_1fr_1fr]">
            <div className="sm:col-span-2 md:col-span-1">
              <Logo />
              <p className="mt-2 max-w-[34ch]">Transforming businesses through intelligent automation solutions.</p>
            </div>
            <div>
              <h2 className="text-lg text-snow">Quick Links</h2>
              <ul className="mt-2">
                {[{ label: 'Home', href: '#top' }, ...navLinks].map(({ label, href }) => (
                  <li key={label}>
                    <a href={href} className="inline-block py-2 hover:text-mint">
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h2 className="text-lg text-snow">Connect With Us</h2>
              <ul className="mt-2">
                <li>
                  <a href="mailto:realassisthq@gmail.com" className="inline-block py-2 hover:text-mint">
                    Email
                  </a>
                </li>
                <li>
                  <a
                    href="https://www.facebook.com/profile.php?id=61596595396695"
                    {...newTab}
                    className="inline-block py-2 hover:text-mint"
                  >
                    Facebook
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="mt-12 flex flex-wrap gap-x-7 gap-y-1 border-t border-[#2c4468] pt-6 text-base">
            <p className="py-2">&copy; {new Date().getFullYear()} Realest AI. All rights reserved.</p>
            <a href="/privacy/" className="py-2 hover:text-mint">
              Privacy Policy
            </a>
            <a href="/data-deletion/" className="py-2 hover:text-mint">
              Data Deletion
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
