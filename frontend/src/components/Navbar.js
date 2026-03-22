import React from 'react';
import { NavLink } from 'react-router-dom';
import './Navbar.css';
import logo from '../logo.svg'; // Assuming logo.svg is in src/

function Navbar() {
    return (
        <nav className="sidebar">
            <div className="logo">
                <img src={logo} alt="New Logo" />
                <span className="sub-logo-text">CCTV_M_J</span>
            </div>
            <ul>
                <li><NavLink to="/">동영상 분석</NavLink></li>
                <li><NavLink to="/streaming">실시간 스트리밍</NavLink></li>
            </ul>
            <div className="footer">
                <p>&copy; GKNU_sphereax_solution.</p>
            </div>
        </nav>
    );
}

export default Navbar;
