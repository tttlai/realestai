import React, { useState, useEffect } from 'react';
import { ArrowRight, ChevronRight, MessageSquare, Zap, Github, Twitter, Linkedin, Menu, X, Lightbulb, MessageCircle, Workflow, Sparkles } from 'lucide-react';

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

  const navLinks = ['About', 'Services', 'Case Studies', 'Contact'];

  const Logo = () => (
    <div className="flex items-center space-x-2">
      <div className="relative">
        <Lightbulb className="w-8 h-8 text-[#64FFDA]" />
        <div className="absolute -top-1 left-1/2 w-3 h-3 bg-[#64FFDA] rounded-full blur-sm" />
      </div>
      <span className="text-white font-bold text-xl tracking-wider">REALEST AI</span>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#0A192F]">
      {/* Navbar */}
      <nav className={`fixed w-full z-50 transition-all duration-300 ${
        isScrolled ? 'bg-[#0A192F]/95 backdrop-blur-sm py-4 shadow-lg' : 'bg-transparent py-6'
      }`}>
        <div className="container mx-auto px-6">
          <div className="flex items-center justify-between">
            <Logo />
            
            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center space-x-8">
              {navLinks.map((link) => (
                <a
                  key={link}
                  href={`#${link.toLowerCase()}`}
                  className="text-[#8892B0] hover:text-[#64FFDA] transition-colors text-sm font-medium"
                >
                  {link}
                </a>
              ))}
              <a
                href="#contact"
                className="bg-[#64FFDA]/10 hover:bg-[#64FFDA]/20 text-[#64FFDA] px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                Schedule a Call
              </a>
            </div>

            {/* Mobile Menu Button */}
            <button 
              className="md:hidden text-[#8892B0] hover:text-[#64FFDA] transition-colors"
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
                  className="text-[#8892B0] hover:text-[#64FFDA] transition-colors text-sm font-medium"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  {link}
                </a>
              ))}
              <a
                href="#contact"
                className="bg-[#64FFDA]/10 hover:bg-[#64FFDA]/20 text-[#64FFDA] px-4 py-2 rounded-lg text-sm font-medium transition-colors text-center"
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
        className="min-h-screen relative flex items-center pt-20"
        style={{
          backgroundImage: 'url("https://images.unsplash.com/photo-1635776062127-d379bfcba9f8?auto=format&fit=crop&q=80")',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-[#0A192F]/90" />
        <div className="container mx-auto px-6 relative z-10">
          <div className="max-w-3xl">
            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
              Real AI Solutions for Real Business Growth
            </h1>
            <p className="text-xl text-[#8892B0] mb-8">
              Transform your business operations with cutting-edge AI solutions. We build custom automation systems that scale with your needs.
            </p>
            <a
              href="#contact"
              className="bg-[#64FFDA] hover:bg-[#64FFDA]/90 text-[#0A192F] px-8 py-4 rounded-lg text-lg font-semibold inline-flex items-center group"
            >
              Schedule a Consultation
              <ArrowRight className="ml-2 group-hover:translate-x-1 transition-transform" />
            </a>
          </div>
        </div>
      </section>

      {/* About Section */}
      <section id="about" className="py-20 bg-[#112240]">
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
              <h2 className="text-4xl font-bold mb-6 text-white">
                Pioneering the Future of Business Automation
              </h2>
              <p className="text-lg text-[#8892B0] mb-8">
                We're not just another automation company. We're pioneers in combining artificial intelligence with business processes to create seamless, efficient, and intelligent workflows that transform how businesses operate.
              </p>
              <a href="#services" className="text-[#64FFDA] font-semibold inline-flex items-center group">
                Explore Our Services
                <ChevronRight className="ml-1 group-hover:translate-x-1 transition-transform" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Services Section */}
      <section id="services" className="py-20 bg-[#0A192F]">
        <div className="container mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-16 text-white">
            Our Services
          </h2>
          <div className="grid md:grid-cols-3 gap-12">
            {[
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
              }
            ].map((service, index) => (
              <div key={index} className="p-8 rounded-xl bg-[#112240] shadow-lg hover:shadow-[#64FFDA]/10 hover:shadow-2xl transition-all duration-300">
                {service.icon}
                <h3 className="text-2xl font-bold mt-6 mb-4 text-white">{service.title}</h3>
                <p className="text-[#8892B0]">{service.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials Section */}
      <section id="case-studies" className="py-20 bg-[#64FFDA]/10">
        <div className="container mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-16 text-white">
            Client Success Stories
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                quote: "The AI solutions provided transformed our customer service operations completely.",
                author: "Sarah Johnson",
                role: "CTO, TechCorp"
              },
              {
                quote: "We've seen a 300% increase in efficiency since implementing their automation systems.",
                author: "Michael Chen",
                role: "Operations Director, InnovateCo"
              },
              {
                quote: "Their team's expertise in AI integration is unmatched in the industry.",
                author: "Emily Rodriguez",
                role: "CEO, FutureScale"
              }
            ].map((testimonial, index) => (
              <div key={index} className="bg-[#112240] p-8 rounded-lg shadow-lg">
                <MessageSquare className="w-10 h-10 text-[#64FFDA] mb-4" />
                <p className="text-white mb-6">{testimonial.quote}</p>
                <div>
                  <p className="font-bold text-white">{testimonial.author}</p>
                  <p className="text-[#8892B0]">{testimonial.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section id="contact" 
        className="py-20 relative"
        style={{
          backgroundImage: 'url("https://images.unsplash.com/photo-1635776062127-d379bfcba9f8?auto=format&fit=crop&q=80")',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-[#0A192F]/95" />
        <div className="container mx-auto px-6 relative z-10 text-center">
          <h2 className="text-4xl font-bold text-white mb-8">
            Ready to Transform Your Business?
          </h2>
          <p className="text-xl text-[#8892B0] mb-8 max-w-2xl mx-auto">
            Join the hundreds of businesses already leveraging our AI solutions to stay ahead of the competition.
          </p>
          <button className="bg-[#64FFDA] hover:bg-[#64FFDA]/90 text-[#0A192F] px-8 py-4 rounded-lg text-lg font-semibold inline-flex items-center group">
            Schedule a Demo
            <Zap className="ml-2 group-hover:translate-x-1 transition-transform" />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#0A192F] text-white py-16">
        <div className="container mx-auto px-6">
          <div className="grid md:grid-cols-3 gap-12">
            <div>
              <Logo />
              <p className="text-[#8892B0] mt-4">
                Transforming businesses through intelligent automation solutions.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Quick Links</h4>
              <ul className="space-y-2">
                {['Home', 'About', 'Services', 'Case Studies', 'Contact'].map((link) => (
                  <li key={link}>
                    <a href="#" className="text-[#8892B0] hover:text-[#64FFDA] transition-colors">
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Connect With Us</h4>
              <div className="flex space-x-4">
                {[
                  { icon: <Twitter className="w-6 h-6" />, label: 'Twitter' },
                  { icon: <Linkedin className="w-6 h-6" />, label: 'LinkedIn' },
                  { icon: <Github className="w-6 h-6" />, label: 'GitHub' }
                ].map((social) => (
                  <a
                    key={social.label}
                    href="#"
                    className="text-[#8892B0] hover:text-[#64FFDA] transition-colors"
                    aria-label={social.label}
                  >
                    {social.icon}
                  </a>
                ))}
              </div>
            </div>
          </div>
          <div className="border-t border-[#112240] mt-12 pt-8 text-center text-[#8892B0]">
            <p>&copy; {new Date().getFullYear()} Realest AI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;