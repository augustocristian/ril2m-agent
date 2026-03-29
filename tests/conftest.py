"""Shared pytest fixtures for RIL2M agent tests."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def maven_project(tmp_path: Path) -> Path:
    """Create a minimal Maven project with Java test files for testing."""
    # Create Maven structure
    test_dir = tmp_path / "src" / "test" / "java" / "com" / "example"
    test_dir.mkdir(parents=True)

    # pom.xml
    (tmp_path / "pom.xml").write_text(
        '<?xml version="1.0"?>\n<project><modelVersion>4.0.0</modelVersion>'
        "<groupId>com.example</groupId><artifactId>test</artifactId>"
        "<version>1.0</version></project>\n"
    )

    # Test file WITH @AccessMode annotations
    (test_dir / "AnnotatedTest.java").write_text(
        '''\
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class AnnotatedTest {

    @AccessMode("READONLY")
    @Test
    public void testFindAllUsers() {
        List<User> users = userRepository.findAll();
        assertNotNull(users);
        assertFalse(users.isEmpty());
    }

    @AccessMode("READWRITE")
    @Test
    public void testCreateUser() {
        User user = new User("test@example.com");
        User saved = userRepository.save(user);
        assertNotNull(saved.getId());
        assertEquals("test@example.com", saved.getEmail());
    }

    @AccessMode("READWRITE")
    @Test
    public void testDeleteUser() {
        userRepository.deleteById(1L);
        assertFalse(userRepository.existsById(1L));
    }

    @AccessMode("READONLY")
    @Test
    public void testCountUsers() {
        long count = userRepository.count();
        assertTrue(count >= 0);
    }
}
'''
    )

    # Test file WITHOUT @AccessMode annotations
    (test_dir / "UnannotatedTest.java").write_text(
        '''\
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class UnannotatedTest {

    @Test
    public void testGetUserById() {
        User user = userRepository.findById(1L).orElse(null);
        assertNotNull(user);
    }

    @Test
    public void testUpdateUserEmail() {
        User user = userRepository.findById(1L).orElse(null);
        user.setEmail("new@example.com");
        userRepository.save(user);
        User updated = userRepository.findById(1L).orElse(null);
        assertEquals("new@example.com", updated.getEmail());
    }

    @Test
    public void testListActiveUsers() {
        List<User> active = userRepository.findByActiveTrue();
        assertNotNull(active);
    }
}
'''
    )

    return tmp_path


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """A directory with no Maven project."""
    return tmp_path
