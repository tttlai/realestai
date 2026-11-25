import React, { useState, useEffect } from 'react';
import { ArrowRight, ChevronRight, MessageSquare, Zap, Github, Twitter, Linkedin, Menu, X, Lightbulb, MessageCircle, Workflow, Sparkles, Home, Calendar, CheckCircle, Clock, Users, Bell } from 'lucide-react';

function App() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = ['About', 'Services', 'Contact'];

  const Logo = () => (
    <div className="flex items-center space-x-2">
      <div className="relative">
        <Lightbulb className="w-8 h-8 text-[#64FFDA]" />
        <div className="absolute -top-1 left-1/2 w-3 h-3 bg-[#64FFDA] rounded-full blur-sm" />
      </div>
      <span className="text-gray-800 dark:text-white font-bold text-xl tracking-wider">REALEST AI</span>
    </div>
  );

  const services = [
    {
      icon: <MessageCircle className="w-12 h-12 text-[#64FFDA]" />,
      title: "AI Customer Service",
      description: "Intelligent agents that handle customer inquiries 24/7 with human-like understanding"
    },
    {
      icon: <Workflow className="w-12 h-12 text-[#64FFDA]" />,
      title: "Workflow Automation",
      description: "Smart agents that streamline and automate your business processes end-to-end"
    },
    {
      icon: <Sparkles className="w-12 h-12 text-[#64FFDA]" />,
      title: "Custom AI Agents",
      description: "Tailored AI agents designed for your specific business needs and objectives"
    },
    {
      icon: <MessageSquare className="w-12 h-12 text-[#64FFDA]" />,
      title: "Automate Documentation",
      description: "AI-powered systems that generate, update, and maintain technical documentation automatically"
    }
  ];

  const featuredServices = [
    {
      icon: <Home className="w-12 h-12 text-[#64FFDA]" />,
      title: "Real Estate & Airbnb Automation",
      description: "End-to-end automation for property management and bookings",
      features: [
        {
          icon: <MessageCircle className="w-6 h-6" />,
          title: "Automated Guest Communication",
          description: "WhatsApp integration for instant responses, automated PDF sharing, and seamless guest interaction"
        },
        {
          icon: <Calendar className="w-6 h-6" />,
          title: "Smart Booking Management",
          description: "Synchronized calendars across platforms, automated payment verification, and booking confirmation"
        },
        {
          icon: <CheckCircle className="w-6 h-6" />,
          title: "Streamlined Check-in",
          description: "Automated security code generation, smart lock integration, and welcome message distribution"
        }
      ]
    },
    {
      icon: <Clock className="w-12 h-12 text-[#64FFDA]" />,
      title: "AI-Powered Appointment Scheduler",
      description: "Smart scheduling solution for service-based businesses",
      features: [
        {
          icon: <Users className="w-6 h-6" />,
          title: "Intelligent Client Management",
          description: "AI-driven scheduling that learns from client preferences and automatically suggests optimal time slots"
        },
        {
          icon: <Bell className="w-6 h-6" />,
          title: "Smart Notifications",
          description: "Automated reminders, rescheduling assistance, and follow-up communications"
        },
        {
          icon: <Calendar className="w-6 h-6" />,
          title: "Resource Optimization",
          description: "Dynamic scheduling that maximizes staff utilization and minimizes downtime"
        }
      ]
    }
  ];

  const consultationLink = "https://cal.com/trishal-suvarna-zo4ibc/30min";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="fixed w-full z-50 bg-white/80 backdrop-blur-md py-6 shadow-md transition-all duration-300">
        <div className="container mx-auto px-6">
          <div className="flex items-center justify-between">
            <Logo />
            
            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center space-x-8">
              {navLinks.map((link) => (
                <a
                  key={link}
                  href={`#${link.toLowerCase()}`}
                  className="text-gray-600 hover:text-[#64FFDA] transition-colors text-sm font-medium"
                >
                  {link}
                </a>
              ))}
              <a
                href={consultationLink}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-[#64FFDA]/10 hover:bg-[#64FFDA]/20 text-[#2A9D8F] px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                Schedule a Call
              </a>
            </div>

            {/* Mobile Menu Button */}
            <button 
              className="md:hidden text-gray-600 hover:text-[#64FFDA] transition-colors"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              {isMobileMenuOpen ? <X /> : <Menu />}
            </button>
          </div>

          {/* Mobile Navigation */}
          <div className={`md:hidden transition-all duration-300 overflow-hidden ${
            isMobileMenuOpen ? 'max-h-64 mt-4' : 'max-h-0'
          }`}>
            <div className="flex flex-col space-y-4 py-4">
              {navLinks.map((link) => (
                <a
                  key={link}
                  href={`#${link.toLowerCase()}`}
                  className="text-gray-600 hover:text-[#64FFDA] transition-colors text-sm font-medium"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  {link}
                </a>
              ))}
              <a
                href={consultationLink}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-[#64FFDA]/10 hover:bg-[#64FFDA]/20 text-[#2A9D8F] px-4 py-2 rounded-lg text-sm font-medium transition-colors text-center"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                Schedule a Call
              </a>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section 
        className="min-h-screen relative flex items-center pt-20 border-b border-gray-200"
        style={{
          backgroundImage: 'url("https://images.unsplash.com/photo-1635776062127-d379bfcba9f8?auto=format&fit=crop&q=80")',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-b from-gray-900/75 to-gray-900/90" />
        <div className="container mx-auto px-6 relative z-10">
          <div className="max-w-3xl">
            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
              Real AI Solutions for Real Business Growth
            </h1>
            <p className="text-xl text-gray-200 mb-8">
              Transform your business operations with cutting-edge AI solutions. We build custom automation systems that scale with your needs.
            </p>
            <a
              href={consultationLink}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-[#64FFDA] hover:bg-[#64FFDA]/90 text-gray-900 px-8 py-4 rounded-lg text-lg font-semibold inline-flex items-center group"
            >
              Schedule a Consultation
              <ArrowRight className="ml-2 group-hover:translate-x-1 transition-transform" />
            </a>
          </div>
        </div>
      </section>

      {/* About Section */}
      <section id="about" className="py-20 bg-white border-b border-gray-200">
        <div className="container mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <img 
                src="https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&q=80" 
                alt="AI Technology"
                className="rounded-lg shadow-xl"
              />
            </div>
            <div>
              <h2 className="text-4xl font-bold mb-6 text-gray-900">
                Pioneering the Future of Business Automation
              </h2>
              <p className="text-lg text-gray-600 mb-8">
                We're not just another automation company. We're pioneers in combining artificial intelligence with business processes to create seamless, efficient, and intelligent workflows that transform how businesses operate.
              </p>
              <a href="#services" className="text-[#2A9D8F] font-semibold inline-flex items-center group">
                Explore Our Services
                <ChevronRight className="ml-1 group-hover:translate-x-1 transition-transform" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Services Section */}
      <section id="services" className="py-20 bg-gray-50/50 border-b border-gray-200">
        <div className="container mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-16 text-gray-900">
            Our Services
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {services.map((service, index) => (
              <div key={index} className="p-8 rounded-xl bg-white shadow-lg hover:shadow-xl transition-all duration-300 border border-gray-100">
                <div>
                  {service.icon}
                  <h3 className="text-2xl font-bold mt-6 mb-4 text-gray-900">{service.title}</h3>
                  <p className="text-gray-600">{service.description}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Links to the static page in public/brokers/ */}
          <a
            href="/brokers/"
            className="group mt-8 p-8 rounded-xl bg-white shadow-lg hover:shadow-xl transition-all duration-300 border border-gray-100 flex flex-col md:flex-row md:items-center gap-6"
          >
            <Home className="w-12 h-12 text-[#64FFDA] flex-shrink-0" />
            <div className="flex-grow">
              <h3 className="text-2xl font-bold mb-2 text-gray-900">WhatsApp Assistant for Property Brokers</h3>
              <p className="text-gray-600">Answers property enquiries day or night, finds out what buyers need, and alerts you when someone wants a visit</p>
            </div>
            <span className="text-[#2A9D8F] font-semibold inline-flex items-center flex-shrink-0">
              See how it works
              <ChevronRight className="ml-1 group-hover:translate-x-1 transition-transform" />
            </span>
          </a>

          {/* Featured Services with Horizontal Scroll */}
          <div className="mt-16">
            <h3 className="text-2xl font-bold text-center mb-8 text-gray-900">
              Featured Solutions
            </h3>
            <div className="relative">
              <div className="overflow-x-auto pb-8 hide-scrollbar">
                <div className="flex space-x-8 px-4">
                  {featuredServices.map((service, index) => (
                    <div key={index} className="flex-none w-full md:w-[600px] p-8 rounded-xl bg-white shadow-lg hover:shadow-xl transition-all duration-300 border border-gray-100">
                      <div className="grid md:grid-cols-2 gap-8">
                        <div>
                          {service.icon}
                          <h3 className="text-2xl font-bold mt-6 mb-4 text-gray-900">{service.title}</h3>
                          <p className="text-gray-600">{service.description}</p>
                        </div>
                        <div className="mt-8 md:mt-0">
                          <div className="grid gap-6">
                            {service.features.map((feature, fIndex) => (
                              <div key={fIndex} className="flex items-start space-x-4 p-4 rounded-lg bg-gray-50 border border-gray-100">
                                <div className="flex-shrink-0 mt-1 text-[#64FFDA]">
                                  {feature.icon}
                                </div>
                                <div>
                                  <h4 className="text-lg font-semibold text-gray-900 mb-2">{feature.title}</h4>
                                  <p className="text-gray-600">{feature.description}</p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section id="contact" 
        className="py-20 relative border-b border-gray-200"
        style={{
          backgroundImage: 'url("https://images.unsplash.com/photo-1635776062127-d379bfcba9f8?auto=format&fit=crop&q=80")',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-gray-900/90 to-gray-900/75" />
        <div className="container mx-auto px-6 relative z-10 text-center">
          <h2 className="text-4xl font-bold text-white mb-8">
            Ready to Transform Your Business?
          </h2>
          <p className="text-xl text-gray-200 mb-8 max-w-2xl mx-auto">
            Join the hundreds of businesses already leveraging our AI solutions to stay ahead of the competition.
          </p>
          <a
            href={consultationLink}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-[#64FFDA] hover:bg-[#64FFDA]/90 text-gray-900 px-8 py-4 rounded-lg text-lg font-semibold inline-flex items-center group"
          >
            Schedule a Demo
            <Zap className="ml-2 group-hover:translate-x-1 transition-transform" />
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-white text-gray-600 py-16">
        <div className="container mx-auto px-6">
          <div className="grid md:grid-cols-3 gap-12">
            <div>
              <Logo />
              <p className="text-gray-500 mt-4">
                Transforming businesses through intelligent automation solutions.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4 text-gray-900">Quick Links</h4>
              <ul className="space-y-2">
                {['Home', 'About', 'Services', 'Contact'].map((link) => (
                  <li key={link}>
                    <a href="#" className="text-gray-500 hover:text-[#64FFDA] transition-colors">
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4 text-gray-900">Connect With Us</h4>
              <div className="flex space-x-4">
                {[
                  { icon: <Twitter className="w-6 h-6" />, label: 'Twitter' },
                  { icon: <Linkedin className="w-6 h-6" />, label: 'LinkedIn' },
                  { icon: <Github className="w-6 h-6" />, label: 'GitHub' }
                ].map((social) => (
                  <a
                    key={social.label}
                    href="#"
                    className="text-gray-500 hover:text-[#64FFDA] transition-colors"
                    aria-label={social.label}
                  >
                    {social.icon}
                  </a>
                ))}
              </div>
            </div>
          </div>
          <div className="border-t border-gray-100 mt-12 pt-8 text-center text-gray-500">
            <p>&copy; {new Date().getFullYear()} Realest AI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;