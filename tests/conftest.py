"""Shared pytest fixtures for RIL2M agent tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def maven_project(tmp_path: Path) -> Path:
    """Create a minimal Maven project with RETORCH-style Java test files."""
    test_dir = tmp_path / "src" / "test" / "java" / "com" / "example"
    test_dir.mkdir(parents=True)
    resources_dir = tmp_path / "src" / "test" / "resources"
    resources_dir.mkdir(parents=True)

    # pom.xml
    (tmp_path / "pom.xml").write_text(
        '<?xml version="1.0"?>\n<project><modelVersion>4.0.0</modelVersion>'
        "<groupId>com.example</groupId><artifactId>test</artifactId>"
        "<version>1.0</version></project>\n"
    )

    # SystemResources.json
    (resources_dir / "ExampleSystemResources.json").write_text(
        json.dumps([
            {"resID": "LoginService", "name": "Login Service", "type": "service"},
            {"resID": "OpenVidu", "name": "OpenVidu Server", "type": "service"},
            {"resID": "Course", "name": "Course Resource", "type": "entity"},
            {"resID": "Database", "name": "MySQL Database", "type": "database"},
        ])
    )

    # Test file WITH RETORCH @AccessMode annotations
    (test_dir / "AnnotatedTest.java").write_text(
        '''\
package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import static org.junit.jupiter.api.Assertions.*;

public class AnnotatedTest {

    @AccessMode(resID = "LoginService", concurrency = 10, sharing = true, accessMode = "READONLY")
    @AccessMode(resID = "Course", concurrency = 10, sharing = true, accessMode = "READONLY")
    @Test
    public void testViewCourse() {
        this.user = setupBrowser("chrome", TJOB_NAME, usermail, WAIT_SECONDS);
        driver = user.getDriver();
        this.slowLogin(user, usermail, password);
        driver.findElement(By.id("course-list")).click();
    }

    @AccessMode(resID = "LoginService", concurrency = 10, sharing = true, accessMode = "READONLY")
    @AccessMode(resID = "OpenVidu", concurrency = 10, sharing = true, accessMode = "NOACCESS")
    @AccessMode(resID = "Course", concurrency = 1, sharing = false, accessMode = "READWRITE")
    @ParameterizedTest
    @MethodSource("data")
    void forumNewEntryTest(String usermail, String password, String role) {
        this.user = setupBrowser("chrome", TJOB_NAME, usermail, WAIT_SECONDS);
        driver = user.getDriver();
        this.slowLogin(user, usermail, password);
        driver.findElement(By.id("new-entry-btn")).click();
        driver.findElement(By.id("entry-title")).sendKeys("Test Entry");
        driver.findElement(By.id("submit-btn")).click();
    }

    @AccessMode(resID = "Database", concurrency = 1, sharing = false, accessMode = "READWRITE")
    @Test
    public void testDeleteRecord() {
        repository.deleteById(1L);
        assertFalse(repository.existsById(1L));
    }
}
'''
    )

    # Test file WITHOUT @AccessMode annotations
    (test_dir / "UnannotatedTest.java").write_text(
        '''\
package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import static org.junit.jupiter.api.Assertions.*;

public class UnannotatedTest {

    @ParameterizedTest
    @MethodSource("data")
    void forumLoadEntriesTest(String usermail, String password, String role) {
        this.user = setupBrowser("chrome", TJOB_NAME + "_" + TEST_NAME, usermail, WAIT_SECONDS);
        driver = user.getDriver();
        this.slowLogin(user, usermail, password);
    }

    @Test
    public void testEditCourse() {
        this.user = setupBrowser("chrome", TJOB_NAME, usermail, WAIT_SECONDS);
        driver = user.getDriver();
        this.slowLogin(user, usermail, password);
        driver.findElement(By.id("edit-course")).click();
        driver.findElement(By.id("save-btn")).click();
    }

    @Test
    public void testCheckDatabase() {
        long count = repository.count();
        assertTrue(count >= 0);
    }
}
'''
    )

    return tmp_path


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """A directory with no Maven project."""
    return tmp_path
