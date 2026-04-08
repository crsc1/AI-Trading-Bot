/* @refresh reload */
import { render } from 'solid-js/web';
import { Router, Route } from '@solidjs/router';
import { Layout } from './components/shared/Layout';
import './styles/globals.css';

const root = document.getElementById('root');

// Layout renders all pages permanently (no mount/unmount).
// Routes exist only so useLocation() returns the current path.
const Noop = () => null;

render(
  () => (
    <Router root={Layout}>
      <Route path="/" component={Noop} />
      <Route path="/charts" component={Noop} />
      <Route path="/flow" component={Noop} />
      <Route path="/agent" component={Noop} />
      <Route path="/reference" component={Noop} />
      <Route path="/scanner" component={Noop} />
    </Router>
  ),
  root!
);
