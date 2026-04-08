/* @refresh reload */
import { render } from 'solid-js/web';
import { Router, Route } from '@solidjs/router';
import { Layout } from './components/shared/Layout';
import { Dashboard } from './components/pages/Dashboard';
import { Charts } from './components/pages/Charts';
import { Flow } from './components/pages/Flow';
import { Agent } from './components/pages/Agent';
import { Reference } from './components/pages/Reference';
import './styles/globals.css';

const root = document.getElementById('root');

render(
  () => (
    <Router root={Layout}>
      <Route path="/" component={Dashboard} />
      <Route path="/charts" component={Charts} />
      <Route path="/flow" component={Flow} />
      <Route path="/agent" component={Agent} />
      <Route path="/reference" component={Reference} />
    </Router>
  ),
  root!
);
