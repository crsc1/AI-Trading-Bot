/* @refresh reload */
import { render } from 'solid-js/web';
import { Router, Route } from '@solidjs/router';
import { Dashboard } from './components/pages/Dashboard';
import { Reference } from './components/pages/Reference';
import './styles/globals.css';

const root = document.getElementById('root');

render(
  () => (
    <Router>
      <Route path="/" component={Dashboard} />
      <Route path="/reference" component={Reference} />
    </Router>
  ),
  root!
);
