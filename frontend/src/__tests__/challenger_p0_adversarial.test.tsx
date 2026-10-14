import React, { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

// 1. Radix UI primitives
import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Slot, Slottable } from '@radix-ui/react-slot';
import * as Switch from '@radix-ui/react-switch';
import * as Tabs from '@radix-ui/react-tabs';
import * as Toast from '@radix-ui/react-toast';
import * as Tooltip from '@radix-ui/react-tooltip';

// 2. Class and styling utilities
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

// 3. Command palette primitive
import { Command } from 'cmdk';

// 4. Icons
import {
  Search,
  Settings,
  Trash2,
  Plus,
  Moon,
  Sun,
  Loader2,
  Check,
  X,
  MessageSquare,
} from 'lucide-react';

describe('Phase 0 Adversarial Challenge: Package Imports & Component Usability', () => {
  it('imports and uses clsx and tailwind-merge with conflict resolution', () => {
    // Basic clsx
    const class1 = clsx('base-class', true && 'active-class', false && 'hidden-class', {
      'conditional-class': true,
      'falsy-class': false,
    });
    expect(class1).toBe('base-class active-class conditional-class');

    // tailwind-merge conflict resolution (e.g. px-2 vs px-4, text-red-500 vs text-blue-500)
    const merged = twMerge('px-2 py-1 bg-red-500 text-sm', 'px-4 bg-blue-500 text-lg');
    expect(merged).toContain('px-4');
    expect(merged).not.toContain('px-2');
    expect(merged).toContain('bg-blue-500');
    expect(merged).not.toContain('bg-red-500');
    expect(merged).toContain('text-lg');
    expect(merged).not.toContain('text-sm');

    // Combined helper pattern
    const cn = (...inputs: any[]) => twMerge(clsx(inputs));
    expect(cn('p-4', undefined, null, false, 'p-8')).toBe('p-8');
  });

  it('renders Lucide React SVG icons with custom props', () => {
    render(
      <div data-testid="icons-container">
        <Search data-testid="icon-search" size={20} className="text-gray-400" />
        <Settings data-testid="icon-settings" size={24} strokeWidth={1.5} />
        <Trash2 data-testid="icon-trash" size={16} />
        <Plus data-testid="icon-plus" />
        <Moon data-testid="icon-moon" />
        <Sun data-testid="icon-sun" />
        <Loader2 data-testid="icon-loader" className="animate-spin" />
        <Check data-testid="icon-check" />
        <X data-testid="icon-x" />
        <MessageSquare data-testid="icon-message" />
      </div>
    );

    const searchIcon = screen.getByTestId('icon-search');
    expect(searchIcon).toBeInTheDocument();
    expect(searchIcon.tagName.toLowerCase()).toBe('svg');
    expect(searchIcon).toHaveAttribute('width', '20');
    expect(searchIcon).toHaveAttribute('height', '20');

    const loaderIcon = screen.getByTestId('icon-loader');
    expect(loaderIcon).toHaveClass('animate-spin');
  });

  it('renders and interacts with @radix-ui/react-dialog', async () => {
    const user = userEvent.setup();

    const TestDialog = () => (
      <Dialog.Root>
        <Dialog.Trigger asChild>
          <button data-testid="dialog-trigger">Open Modal</button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay data-testid="dialog-overlay" />
          <Dialog.Content data-testid="dialog-content">
            <Dialog.Title data-testid="dialog-title">Test Modal Title</Dialog.Title>
            <Dialog.Description data-testid="dialog-desc">
              Test Modal Description
            </Dialog.Description>
            <Dialog.Close asChild>
              <button data-testid="dialog-close">Close Modal</button>
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );

    render(<TestDialog />);

    // Content should initially not be open
    expect(screen.queryByTestId('dialog-content')).not.toBeInTheDocument();

    // Click trigger to open dialog
    await user.click(screen.getByTestId('dialog-trigger'));

    expect(screen.getByTestId('dialog-content')).toBeInTheDocument();
    expect(screen.getByTestId('dialog-title')).toHaveTextContent('Test Modal Title');
    expect(screen.getByTestId('dialog-desc')).toHaveTextContent('Test Modal Description');

    // Click close button
    await user.click(screen.getByTestId('dialog-close'));
    expect(screen.queryByTestId('dialog-content')).not.toBeInTheDocument();
  });

  it('renders and interacts with @radix-ui/react-switch', async () => {
    const user = userEvent.setup();

    const TestSwitch = () => {
      const [checked, setChecked] = useState(false);
      return (
        <div>
          <span data-testid="switch-status">{checked ? 'ON' : 'OFF'}</span>
          <Switch.Root
            data-testid="switch-root"
            checked={checked}
            onCheckedChange={setChecked}
          >
            <Switch.Thumb data-testid="switch-thumb" />
          </Switch.Root>
        </div>
      );
    };

    render(<TestSwitch />);

    expect(screen.getByTestId('switch-status')).toHaveTextContent('OFF');
    expect(screen.getByTestId('switch-root')).toHaveAttribute('data-state', 'unchecked');

    await user.click(screen.getByTestId('switch-root'));
    expect(screen.getByTestId('switch-status')).toHaveTextContent('ON');
    expect(screen.getByTestId('switch-root')).toHaveAttribute('data-state', 'checked');

    await user.click(screen.getByTestId('switch-root'));
    expect(screen.getByTestId('switch-status')).toHaveTextContent('OFF');
  });

  it('renders and interacts with @radix-ui/react-tabs', async () => {
    const user = userEvent.setup();

    const TestTabs = () => (
      <Tabs.Root defaultValue="tab1" data-testid="tabs-root">
        <Tabs.List data-testid="tabs-list">
          <Tabs.Trigger value="tab1" data-testid="tab1-trigger">Tab 1</Tabs.Trigger>
          <Tabs.Trigger value="tab2" data-testid="tab2-trigger">Tab 2</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="tab1" data-testid="tab1-content">
          Content of Tab 1
        </Tabs.Content>
        <Tabs.Content value="tab2" data-testid="tab2-content">
          Content of Tab 2
        </Tabs.Content>
      </Tabs.Root>
    );

    render(<TestTabs />);

    expect(screen.getByTestId('tab1-content')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('tab1-content')).not.toHaveAttribute('hidden');
    expect(screen.getByTestId('tab2-content')).toHaveAttribute('data-state', 'inactive');
    expect(screen.getByTestId('tab2-content')).toHaveAttribute('hidden');

    await user.click(screen.getByTestId('tab2-trigger'));
    expect(screen.getByTestId('tab1-content')).toHaveAttribute('data-state', 'inactive');
    expect(screen.getByTestId('tab1-content')).toHaveAttribute('hidden');
    expect(screen.getByTestId('tab2-content')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('tab2-content')).not.toHaveAttribute('hidden');
  });

  it('renders @radix-ui/react-slot and merges props properly', () => {
    const CustomButton: React.FC<{ asChild?: boolean; children: React.ReactNode; [key: string]: any }> = ({
      asChild,
      children,
      ...props
    }) => {
      const Comp = asChild ? Slot : 'button';
      return <Comp {...props}>{children}</Comp>;
    };

    render(
      <CustomButton asChild className="btn-base" data-testid="slot-button">
        <a href="/test" className="btn-link">
          <Slottable>Click me</Slottable>
        </a>
      </CustomButton>
    );

    const link = screen.getByTestId('slot-button');
    expect(link.tagName.toLowerCase()).toBe('a');
    expect(link).toHaveAttribute('href', '/test');
    expect(link).toHaveClass('btn-base');
    expect(link).toHaveClass('btn-link');
    expect(link).toHaveTextContent('Click me');
  });

  it('renders and interacts with cmdk command palette', async () => {
    const user = userEvent.setup();

    const TestCommand = () => {
      const [selected, setSelected] = useState('');
      return (
        <div>
          <div data-testid="selected-item">Selected: {selected}</div>
          <Command data-testid="command-root">
            <Command.Input placeholder="Search actions..." data-testid="command-input" />
            <Command.List data-testid="command-list">
              <Command.Empty data-testid="command-empty">No results found.</Command.Empty>
              <Command.Group heading="Suggestions" data-testid="command-group">
                <Command.Item
                  onSelect={() => setSelected('New Chat')}
                  data-testid="item-new-chat"
                >
                  New Chat
                </Command.Item>
                <Command.Item
                  onSelect={() => setSelected('Settings')}
                  data-testid="item-settings"
                >
                  Settings
                </Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </div>
      );
    };

    render(<TestCommand />);

    expect(screen.getByTestId('command-root')).toBeInTheDocument();
    expect(screen.getByTestId('item-new-chat')).toBeInTheDocument();
    expect(screen.getByTestId('item-settings')).toBeInTheDocument();

    // Type in search box to filter
    await user.type(screen.getByTestId('command-input'), 'Settings');
    expect(screen.getByTestId('item-settings')).toBeInTheDocument();

    // cmdk hides non-matching items by styling or aria-hidden
    await user.click(screen.getByTestId('item-settings'));
    expect(screen.getByTestId('selected-item')).toHaveTextContent('Selected: Settings');
  });

  it('renders and interacts with @radix-ui/react-dropdown-menu', async () => {
    const user = userEvent.setup();
    const onSelectAction = vi.fn();

    const TestDropdown = () => (
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button data-testid="menu-trigger">Options</button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content data-testid="menu-content">
            <DropdownMenu.Item
              data-testid="menu-item-1"
              onSelect={onSelectAction}
            >
              Action 1
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item data-testid="menu-item-2">
              Action 2
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    );

    render(<TestDropdown />);

    expect(screen.queryByTestId('menu-content')).not.toBeInTheDocument();
    await user.click(screen.getByTestId('menu-trigger'));

    expect(screen.getByTestId('menu-content')).toBeInTheDocument();
    expect(screen.getByTestId('menu-item-1')).toHaveTextContent('Action 1');
    expect(screen.getByTestId('menu-item-2')).toHaveTextContent('Action 2');

    await user.click(screen.getByTestId('menu-item-1'));
    expect(onSelectAction).toHaveBeenCalledTimes(1);
  });

  it('renders and interacts with @radix-ui/react-tooltip', async () => {
    const user = userEvent.setup();

    const TestTooltip = () => (
      <Tooltip.Provider delayDuration={0}>
        <Tooltip.Root>
          <Tooltip.Trigger asChild>
            <button data-testid="tooltip-trigger">Hover Me</button>
          </Tooltip.Trigger>
          <Tooltip.Portal>
            <Tooltip.Content data-testid="tooltip-content">
              Tooltip Information
              <Tooltip.Arrow />
            </Tooltip.Content>
          </Tooltip.Portal>
        </Tooltip.Root>
      </Tooltip.Provider>
    );

    render(<TestTooltip />);

    expect(screen.queryByTestId('tooltip-content')).not.toBeInTheDocument();

    await user.hover(screen.getByTestId('tooltip-trigger'));
    expect(await screen.findByTestId('tooltip-content')).toBeInTheDocument();
    expect(screen.getByTestId('tooltip-content')).toHaveTextContent('Tooltip Information');

    await user.unhover(screen.getByTestId('tooltip-trigger'));
  });

  it('renders and interacts with @radix-ui/react-toast', () => {
    const TestToast = () => {
      const [open, setOpen] = useState(true);
      return (
        <Toast.Provider swipeDirection="right">
          <Toast.Root open={open} onOpenChange={setOpen} data-testid="toast-root">
            <Toast.Title data-testid="toast-title">Notification</Toast.Title>
            <Toast.Description data-testid="toast-desc">Settings saved</Toast.Description>
            <Toast.Close data-testid="toast-close">Dismiss</Toast.Close>
          </Toast.Root>
          <Toast.Viewport data-testid="toast-viewport" />
        </Toast.Provider>
      );
    };

    render(<TestToast />);

    expect(screen.getByTestId('toast-root')).toBeInTheDocument();
    expect(screen.getByTestId('toast-title')).toHaveTextContent('Notification');
    expect(screen.getByTestId('toast-desc')).toHaveTextContent('Settings saved');
  });

  it('verifies Pointer Capture polyfills in setupTests.ts work as expected', () => {
    const el = document.createElement('div');
    expect(typeof el.hasPointerCapture).toBe('function');
    expect(typeof el.setPointerCapture).toBe('function');
    expect(typeof el.releasePointerCapture).toBe('function');

    expect(el.hasPointerCapture(1)).toBe(false);
    expect(() => el.setPointerCapture(1)).not.toThrow();
    expect(() => el.releasePointerCapture(1)).not.toThrow();
  });
});
