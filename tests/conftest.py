"""Shared pytest fixtures for RIL2M agent tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def maven_project(tmp_path: Path) -> Path:
    """Create a minimal Maven project with RETORCH-style Java test files."""
    test_dir = tmp_path / "src" / "test" / "java" / "com" / "example"
    test_dir.mkdir(parents=True)

    # .retorch/ directory with SystemResources.json (real RETORCH dict format)
    retorch_dir = tmp_path / ".retorch"
    retorch_dir.mkdir()

    # pom.xml
    (tmp_path / "pom.xml").write_text(
        '<?xml version="1.0"?>\n<project><modelVersion>4.0.0</modelVersion>'
        "<groupId>com.example</groupId><artifactId>test</artifactId>"
        "<version>1.0</version></project>\n"
    )

    # SystemResources.json in .retorch/ — dict keyed by resource ID
    (retorch_dir / "ExampleSystemResources.json").write_text(
        json.dumps(
            {
                "loginservice": {
                    "hierarchyParent": ["mysql"],
                    "replaceable": [],
                    "elasticityModel": {
                        "elasticityID": "elasmodelLoginService",
                        "elasticity": 5,
                        "elasticityCost": 15.0,
                    },
                    "resourceType": "LOGICAL",
                    "resourceID": "loginservice",
                    "minimalCapacities": [
                        {"name": "memory", "quantity": 0.3},
                        {"name": "processor", "quantity": 0.2},
                        {"name": "storage", "quantity": 0.5},
                    ],
                    "dockerImage": "codeurjc/full-teaching_no-services-openvidu:latest",
                },
                "openvidu": {
                    "hierarchyParent": [],
                    "replaceable": [],
                    "elasticityModel": {
                        "elasticityID": "elasmodelOpenvidu",
                        "elasticity": 3,
                        "elasticityCost": 20.0,
                    },
                    "resourceType": "PHYSICAL",
                    "resourceID": "openvidu",
                    "minimalCapacities": [
                        {"name": "memory", "quantity": 0.5},
                        {"name": "processor", "quantity": 0.3},
                    ],
                    "dockerImage": "openvidu/openvidu-server-kms:2.11.0",
                },
                "course": {
                    "hierarchyParent": ["loginservice"],
                    "replaceable": [],
                    "elasticityModel": {
                        "elasticityID": "elasmodelCourse",
                        "elasticity": 5,
                        "elasticityCost": 10.0,
                    },
                    "resourceType": "LOGICAL",
                    "resourceID": "course",
                    "minimalCapacities": [],
                    "dockerImage": "",
                },
                "mysql": {
                    "hierarchyParent": [],
                    "replaceable": [],
                    "elasticityModel": {
                        "elasticityID": "elasmodelMysql",
                        "elasticity": 2,
                        "elasticityCost": 25.0,
                    },
                    "resourceType": "PHYSICAL",
                    "resourceID": "mysql",
                    "minimalCapacities": [
                        {"name": "memory", "quantity": 0.4},
                        {"name": "storage", "quantity": 1.0},
                    ],
                    "dockerImage": "database;mysql:5.7.21",
                },
            },
            indent=2,
        )
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

    @AccessMode(resID = "loginservice", concurrency = 10, sharing = true, accessMode = "READONLY")
    @AccessMode(resID = "course", concurrency = 10, sharing = true, accessMode = "READONLY")
    @Test
    public void testViewCourse() {
        this.user = setupBrowser("chrome", TJOB_NAME, usermail, WAIT_SECONDS);
        driver = user.getDriver();
        this.slowLogin(user, usermail, password);
        driver.findElement(By.id("course-list")).click();
    }

    @AccessMode(resID = "loginservice", concurrency = 10, sharing = true, accessMode = "READONLY")
    @AccessMode(resID = "openvidu", concurrency = 10, sharing = true, accessMode = "NOACCESS")
    @AccessMode(resID = "course", concurrency = 1, sharing = false, accessMode = "READWRITE")
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

    @AccessMode(resID = "mysql", concurrency = 1, sharing = false, accessMode = "READWRITE")
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
