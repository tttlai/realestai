import { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, ChevronRight, Menu, X, Lightbulb } from 'lucide-react';
import Lamp from './Lamp';

const consultationLink = 'https://cal.com/trishal-suvarna-zo4ibc/30min';
const newTab = { target: '_blank', rel: 'noopener noreferrer' };

const navLinks = [
  { label: 'About', href: '#about' },
  { label: 'Services', href: '#services' },
  { label: 'Contact', href: '#contact' },
];

const services = [
  {
    title: 'AI Customer Service',
    description: 'Intelligent agents that handle customer inquiries 24/7 with human-like understanding',
  },
  {
    title: 'Workflow Automation',
    description: 'Smart agents that streamline and automate your business processes end-to-end',
  },
  {
    title: 'Custom AI Agents',
    description: 'Tailored AI agents designed for your specific business needs and objectives',
  },
  {
    title: 'Automate Documentation',
    description: 'AI-powered systems that generate, update, and maintain technical documentation automatically',
  },
];

// Our own products, shown as panels above the services list.
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

const featuredServices = [
  {
    title: 'Real Estate & Airbnb Automation',
    description: 'End-to-end automation for property management and bookings',
    features: [
      {
        title: 'Automated Guest Communication',
        description: 'WhatsApp integration for instant responses, automated PDF sharing, and seamless guest interaction',
      },
      {
        title: 'Smart Booking Management',
        description: 'Synchronized calendars across platforms, automated payment verification, and booking confirmation',
      },
      {
        title: 'Streamlined Check-in',
        description: 'Automated security code generation, smart lock integration, and welcome message distribution',
      },
    ],
  },
  {
    title: 'AI-Powered Appointment Scheduler',
    description: 'Smart scheduling solution for service-based businesses',
    features: [
      {
        title: 'Intelligent Client Management',
        description: 'AI-driven scheduling that learns from client preferences and automatically suggests optimal time slots',
      },
      {
        title: 'Smart Notifications',
        description: 'Automated reminders, rescheduling assistance, and follow-up communications',
      },
      {
        title: 'Resource Optimization',
        description: 'Dynamic scheduling that maximizes staff utilization and minimizes downtime',
      },
    ],
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

        <section id="about" className="section">
          <div className="wrap grid gap-8 md:grid-cols-[1.15fr_1fr] md:gap-20">
            <h2 className="section-title">Pioneering the Future of Business Automation</h2>
            <div>
              <p className="max-w-[48ch] text-xl leading-relaxed text-ink-soft">
                We're not just another automation company. We're pioneers in combining artificial intelligence with business processes to create seamless, efficient, and intelligent workflows that transform how businesses operate.
              </p>
              <a href="#services" className="mt-5 inline-flex items-center gap-1 py-2 font-bold text-teal">
                Explore Our Services
                <ChevronRight className="arrow" aria-hidden="true" />
              </a>
            </div>
          </div>
        </section>

        <section id="services" className="wrap scroll-mt-8 pb-[clamp(72px,10vw,136px)]">
          <h2 className="section-title">Our Services</h2>
          <ul className="mt-10 grid gap-5 lg:grid-cols-2">
            {products.map(({ title, description, href, cta, external }) => (
              <li key={title}>
                <a
                  href={href}
                  {...(external ? newTab : {})}
                  className="flex h-full flex-col gap-6 rounded-2xl bg-mint-soft p-7 hover:bg-mint md:p-11"
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

          <ul className="mt-12 border-b border-day-line">
            {services.map(({ title, description }) => (
              <li
                key={title}
                className="grid gap-2 border-t border-day-line py-7 md:grid-cols-[1.15fr_1fr] md:items-baseline md:gap-20"
              >
                <h3 className="text-[clamp(1.5rem,1.2rem+1.2vw,2.1rem)]">{title}</h3>
                <p className="max-w-[48ch] text-ink-soft">{description}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="section bg-night text-night-text">
          <div className="wrap">
            <h2 className="section-title text-snow">Featured Solutions</h2>
            {featuredServices.map(({ title, description, features }) => (
              <div
                key={title}
                className="mt-14 grid gap-8 border-t border-[#2c4468] pt-10 md:grid-cols-[1fr_1.4fr] md:gap-20"
              >
                <div>
                  <h3 className="text-[clamp(1.7rem,1.3rem+1.4vw,2.4rem)] text-snow">{title}</h3>
                  <p className="mt-4 max-w-[36ch]">{description}</p>
                </div>
                <dl className="grid gap-7">
                  {features.map((feature) => (
                    <div key={feature.title}>
                      <dt className="text-xl font-bold text-mint">{feature.title}</dt>
                      <dd className="mt-1 max-w-[56ch]">{feature.description}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
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
