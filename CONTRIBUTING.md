# Contributing to HAC Grades

Thank you for your interest in contributing to HAC Grades! This document provides guidelines for contributing to the project.

## Code of Conduct

This project follows the standard open-source code of conduct. Please be respectful and constructive in all interactions.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue on GitHub with:

1. **Clear title** - Describe the issue briefly
2. **Description** - Detailed explanation of the problem
3. **Steps to reproduce** - How to recreate the issue
4. **Expected behavior** - What should happen
5. **Actual behavior** - What actually happens
6. **Environment details**:
   - Home Assistant version
   - Integration version
   - HAC school district (if relevant)
7. **Logs** - Relevant error messages (redact personal information)

### Suggesting Features

Feature requests are welcome! Please create an issue with:

1. **Use case** - Why you need this feature
2. **Proposed solution** - How you envision it working
3. **Alternatives considered** - Other approaches you've thought about

### Submitting Pull Requests

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Update documentation if needed
4. **Test thoroughly**
   - Test with your own HAC instance
   - Verify no breaking changes
   - Check Home Assistant logs for errors
5. **Commit your changes**
   ```bash
   git commit -m "Add feature: description of feature"
   ```
6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```
7. **Create a pull request**
   - Describe what your changes do
   - Reference any related issues
   - Include test results if applicable

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Home Assistant development environment
- Access to a Home Access Center account for testing

### Local Development

1. Clone the repository
   ```bash
   git clone https://github.com/dustinhouseman/HAC-Scraper.git
   cd HAC-Scraper
   ```

2. Set up in your Home Assistant development environment
   ```bash
   ln -s $(pwd)/custom_components/hac_grades ~/.homeassistant/custom_components/hac_grades
   ```

3. Restart Home Assistant

4. Test your changes

### Code Style

- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Write descriptive variable and function names
- Add docstrings to functions and classes
- Keep functions focused and modular

### Testing

Before submitting a PR:

- Test with a real HAC account
- Verify all sensors are created correctly
- Check that entity updates work properly
- Test the force refresh button
- Verify dashboard generation works (if modified)

## Documentation

If your changes affect user-facing functionality:

- Update relevant documentation files
- Add examples where helpful
- Update CHANGELOG.md
- Keep README.md accurate

## Questions?

If you have questions about contributing:

1. Check existing issues and discussions
2. Create a new discussion on GitHub
3. Reach out in the issue comments

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
